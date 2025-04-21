# -*- coding: utf-8 -*-
from qgis.PyQt.QtCore import QCoreApplication, QDate, QDateTime
from qgis.core import (QgsProcessing, QgsProcessingAlgorithm,
                       QgsProcessingParameterFile,
                       QgsProcessingParameterFolderDestination,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterDateTime,
                       QgsProcessingException,
                       QgsProject, 
                       QgsRasterLayer)
import os
import xarray as xr
import numpy as np
import rasterio
from rasterio.transform import from_origin
import re
from datetime import datetime, timedelta

class NetCDFTimeSeriesAlgorithm(QgsProcessingAlgorithm):
    INPUT_FOLDER = 'INPUT_FOLDER'
    OUTPUT_FOLDER = 'OUTPUT_FOLDER'
    START_DATE = 'START_DATE'
    END_DATE = 'END_DATE'
    INTERVAL_HOURS = 'INTERVAL_HOURS'
    OPERATION = 'OPERATION'
    TIME_OFFSET = 'TIME_OFFSET'
    NODATA_THRESHOLD = 'NODATA_THRESHOLD'
    
    def initAlgorithm(self, config=None):
        # Carpeta de entrada con archivos NetCDF
        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT_FOLDER,
                self.tr('Carpeta con archivos NetCDF (incluye subcarpetas)'),
                behavior=QgsProcessingParameterFile.Folder,
                defaultValue=None
            )
        )
        
        # Fecha inicial
        self.addParameter(
            QgsProcessingParameterDateTime(
                self.START_DATE,
                self.tr('Fecha y hora de inicio'),
                type=QgsProcessingParameterDateTime.DateTime,
                defaultValue=QDateTime.currentDateTime().addDays(-1)
            )
        )
        
        # Fecha final
        self.addParameter(
            QgsProcessingParameterDateTime(
                self.END_DATE,
                self.tr('Fecha y hora final'),
                type=QgsProcessingParameterDateTime.DateTime,
                defaultValue=QDateTime.currentDateTime()
            )
        )
        
        # Intervalo en horas
        self.addParameter(
            QgsProcessingParameterNumber(
                self.INTERVAL_HOURS,
                self.tr('Intervalo en horas'),
                type=QgsProcessingParameterNumber.Double,
                defaultValue=24.0,
                minValue=0.1,
                maxValue=720.0  # Hasta 30 días
            )
        )
        
        # Operaciones disponibles
        self.addParameter(
            QgsProcessingParameterEnum(
                self.OPERATION,
                self.tr('Operación estadística'),
                options=['Suma', 'Media', 'Máximo', 'Mínimo'],
                defaultValue=0  # Suma como predeterminado
            )
        )
        
        # Desplazamiento horario (UTC a hora local)
        self.addParameter(
            QgsProcessingParameterNumber(
                self.TIME_OFFSET,
                self.tr('Desplazamiento horario UTC (p.ej. -5 para Ecuador)'),
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=-5,
                minValue=-12,
                maxValue=14  # Rango de zonas horarias
            )
        )
        
        # Umbral para valores NoData
        self.addParameter(
            QgsProcessingParameterNumber(
                self.NODATA_THRESHOLD,
                self.tr('Umbral para valores NoData (dBZ)'),
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=25,
                minValue=0,
                maxValue=250
            )
        )
        
        # Carpeta de salida para los GeoTIFFs
        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_FOLDER,
                self.tr('Carpeta de salida para los GeoTIFFs'),
                optional=True
            )
        )
    
    def processAlgorithm(self, parameters, context, feedback):
        # Obtener parámetros
        input_folder = self.parameterAsFile(parameters, self.INPUT_FOLDER, context)
        output_folder = self.parameterAsFile(parameters, self.OUTPUT_FOLDER, context)
        start_date = self.parameterAsDateTime(parameters, self.START_DATE, context)
        end_date = self.parameterAsDateTime(parameters, self.END_DATE, context)
        interval_hours = self.parameterAsDouble(parameters, self.INTERVAL_HOURS, context)
        operation_idx = self.parameterAsEnum(parameters, self.OPERATION, context)
        time_offset = self.parameterAsInt(parameters, self.TIME_OFFSET, context)
        nodata_threshold = self.parameterAsInt(parameters, self.NODATA_THRESHOLD, context)
        
        # Validar parámetros
        if not input_folder:
            raise QgsProcessingException(self.tr("No se ha seleccionado una carpeta de entrada válida."))
        
        # Si no se especifica una carpeta de salida, crear una en la misma ubicación
        if not output_folder:
            operations = ['suma', 'media', 'max', 'min']
            output_folder = os.path.join(input_folder, f"resultados_ts_{operations[operation_idx]}")
        
        # Crear la carpeta de salida si no existe
        os.makedirs(output_folder, exist_ok=True)
        
        # Mostrar información de los parámetros al usuario
        feedback.pushInfo(f"Procesando carpeta: {input_folder}")
        feedback.pushInfo(f"Carpeta de salida: {output_folder}")
        feedback.pushInfo(f"Fecha de inicio (hora local): {start_date.toString('yyyy-MM-dd HH:mm')}")
        feedback.pushInfo(f"Fecha final (hora local): {end_date.toString('yyyy-MM-dd HH:mm')}")
        feedback.pushInfo(f"Intervalo en horas: {interval_hours}")
        
        # Convertir los QDateTime de PyQt a datetime de Python para facilitar manejo
        start_date_py = start_date.toPyDateTime()
        end_date_py = end_date.toPyDateTime()
        
        # Ajustar fechas con el desplazamiento horario (convertir de hora local a UTC)
        search_start = start_date_py - timedelta(hours=time_offset)
        search_end = end_date_py - timedelta(hours=time_offset)
        
        feedback.pushInfo(f"Hora local: UTC{time_offset:+d}")
        feedback.pushInfo(f"Búsqueda desde (UTC): {search_start.strftime('%Y-%m-%d %H:%M')}")
        feedback.pushInfo(f"Búsqueda hasta (UTC): {search_end.strftime('%Y-%m-%d %H:%M')}")
        
        # Definir la operación a realizar
        operations = ['suma', 'media', 'máximo', 'mínimo']
        selected_operation = operations[operation_idx]
        feedback.pushInfo(f"Operación: {selected_operation}")
        feedback.pushInfo(f"Umbral para valores NoData: {nodata_threshold} dBZ")
        
        try:
            # Buscar todos los archivos NetCDF en la carpeta y subcarpetas
            netcdf_files = []
            for root, dirs, files in os.walk(input_folder):
                for file in files:
                    if file.endswith(('.nc', '.nc4', '.cdf', '.netcdf')):
                        netcdf_files.append(os.path.join(root, file))
            
            if not netcdf_files:
                feedback.reportError("No se encontraron archivos NetCDF en la carpeta o subcarpetas.")
                return {self.OUTPUT_FOLDER: None}
                
            feedback.pushInfo(f"Se encontraron {len(netcdf_files)} archivos NetCDF en total.")
            
            # Filtrar archivos por fecha usando el patrón en los nombres de archivo
            # Patrón típico: contiene YYYYMMDD_HHMM o YYYYMMDDHHMM
            filtered_files = []
            
            for file_path in netcdf_files:
                file_name = os.path.basename(file_path)
                # Intentar extraer la fecha del nombre del archivo
                date_match1 = re.search(r'(\d{4})(\d{2})(\d{2})_?(\d{2})(\d{2})', file_name) # Formato YYYYMMDD_HHMM
                date_match2 = re.search(r'(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})', file_name)   # Formato YYYYMMDDHHMM
                
                if date_match1:
                    year, month, day, hour, minute = map(int, date_match1.groups())
                    file_datetime = datetime(year, month, day, hour, minute)
                elif date_match2:
                    year, month, day, hour, minute = map(int, date_match2.groups())
                    file_datetime = datetime(year, month, day, hour, minute)
                else:
                    feedback.pushInfo(f"No se pudo extraer fecha de: {file_name}, ignorando archivo.")
                    continue
                
                # Comprobar si el archivo está dentro del rango de fechas
                if search_start <= file_datetime <= search_end:
                    # Guardar la ruta y la fecha extraída
                    filtered_files.append((file_path, file_datetime))
            
            # Ordenar archivos por fecha
            filtered_files.sort(key=lambda x: x[1])
            
            if not filtered_files:
                feedback.reportError("No se encontraron archivos dentro del rango de fechas especificado.")
                return {self.OUTPUT_FOLDER: None}
                
            feedback.pushInfo(f"Se encontraron {len(filtered_files)} archivos dentro del rango de fechas.")
            
            # PRIMERA ETAPA: Convertir todos los archivos NetCDF a GeoTIFF individuales
            # Esto replica la funcionalidad de la herramienta GeoTIFF pero sin aplicar paleta de colores
            
            # Crear carpeta para TIFFs temporales
            temp_tiff_folder = os.path.join(output_folder, "tiffs_individuales")
            os.makedirs(temp_tiff_folder, exist_ok=True)
            
            feedback.pushInfo(f"\nEtapa 1: Convirtiendo archivos NetCDF a GeoTIFF individuales...")
            
            # Lista para almacenar rutas de archivos GeoTIFF generados
            tiff_files = []
            
            # Para cada archivo NetCDF, generar un GeoTIFF
            total_files = len(filtered_files)
            
            for idx, (file_path, file_datetime) in enumerate(filtered_files):
                # Verificar si el usuario canceló la operación
                if feedback.isCanceled():
                    break
                    
                # Actualizar progreso
                progress = int((idx / total_files) * 50)  # Primera etapa = 50% del progreso total
                feedback.setProgress(progress)
                
                file_name = os.path.basename(file_path)
                out_tiff_name = os.path.splitext(file_name)[0] + ".tif"
                out_tiff_path = os.path.join(temp_tiff_folder, out_tiff_name)
                
                feedback.pushInfo(f"Procesando archivo {idx+1}/{total_files}: {file_name}")
                
                try:
                    # Abrir el NetCDF
                    ds = xr.open_dataset(file_path)
                    
                    # Extraer datos de reflectividad, latitud y longitud
                    reflectivity = ds['Band1'].values
                    lats = ds['lat'].values
                    lons = ds['lon'].values
                    
                    # Aplicar umbral para valores NoData (solo para visualización, mantenemos datos originales)
                    # Esta vez NO enmascaramos los datos, conservamos todos los valores
                    
                    # Calcular resolución espacial (en grados)
                    res_lon = abs(lons[1] - lons[0])
                    res_lat = abs(lats[1] - lats[0])
                    
                    # Definir la transformación geográfica (origen: esquina superior izquierda)
                    transform = from_origin(
                        lons.min(),  # Longitud mínima (oeste)
                        lats.max(),  # Latitud máxima (norte)
                        res_lon,     # Resolución en longitud
                        res_lat      # Resolución en latitud
                    )
                    
                    # Crear el GeoTIFF
                    with rasterio.open(
                        out_tiff_path,
                        'w',
                        driver='GTiff',
                        height=reflectivity.shape[0],
                        width=reflectivity.shape[1],
                        count=1,
                        dtype=reflectivity.dtype,
                        crs='+proj=longlat +datum=WGS84 +no_defs',  # WGS84
                        transform=transform,
                        nodata=None  # No establecemos NoData, conservamos todos los valores
                    ) as dst:
                        dst.write(reflectivity, 1)
                    
                    # Cerrar dataset
                    ds.close()
                    
                    # Agregar a la lista de TIFFs
                    tiff_files.append((out_tiff_path, file_datetime))
                    
                except Exception as e:
                    feedback.pushWarning(f"Error al procesar {file_name}: {str(e)}")
                    continue
            
            if feedback.isCanceled():
                feedback.pushInfo("Operación cancelada por el usuario.")
                return {self.OUTPUT_FOLDER: None}
                
            if not tiff_files:
                feedback.reportError("No se pudieron generar archivos GeoTIFF intermedios.")
                return {self.OUTPUT_FOLDER: None}
                
            feedback.pushInfo(f"Se generaron {len(tiff_files)} archivos GeoTIFF intermedios.")
            
            # SEGUNDA ETAPA: Agrupar los GeoTIFFs en intervalos y aplicar cálculos estadísticos
            
            feedback.pushInfo(f"\nEtapa 2: Agrupando archivos y calculando estadísticas...")
            
            # Definir intervalos a partir de la fecha de inicio
            intervals = []
            current_interval_start = search_start
            
            while current_interval_start < search_end:
                current_interval_end = current_interval_start + timedelta(hours=interval_hours)
                # Asegurarse de que el último intervalo no exceda la fecha final
                if current_interval_end > search_end:
                    current_interval_end = search_end
                    
                intervals.append((current_interval_start, current_interval_end))
                current_interval_start = current_interval_end
            
            feedback.pushInfo(f"Se generaron {len(intervals)} intervalos para el análisis.")
            
            # Agrupar archivos por intervalos
            interval_files = []
            
            for interval_start, interval_end in intervals:
                files_in_interval = [
                    f[0] for f in tiff_files 
                    if interval_start <= f[1] < interval_end
                ]
                
                if files_in_interval:
                    local_start = interval_start + timedelta(hours=time_offset)
                    local_end = interval_end + timedelta(hours=time_offset)
                    
                    interval_files.append({
                        'start': interval_start,
                        'end': interval_end,
                        'local_start': local_start,
                        'local_end': local_end,
                        'files': files_in_interval
                    })
                    feedback.pushInfo(f"Intervalo {local_start.strftime('%Y-%m-%d %H:%M')} - "
                                     f"{local_end.strftime('%Y-%m-%d %H:%M')} (hora local): "
                                     f"{len(files_in_interval)} archivos")
            
            # Procesar cada intervalo generando un archivo de resultado
            total_intervals = len(interval_files)
            result_files = []
            
            for idx, interval in enumerate(interval_files):
                # Verificar si el usuario canceló la operación
                if feedback.isCanceled():
                    break
                    
                # Actualizar progreso
                progress = 50 + int((idx / total_intervals) * 50)  # Segunda etapa = 50% restante
                feedback.setProgress(progress)
                
                interval_start = interval['start']
                interval_end = interval['end']
                local_start = interval['local_start']
                local_end = interval['local_end']
                interval_files_list = interval['files']
                
                # Formar nombre de archivo basado en fechas locales
                start_str = local_start.strftime('%Y%m%d_%H%M')
                end_str = local_end.strftime('%Y%m%d_%H%M')
                operation_str = operations[operation_idx]
                
                output_filename = f"radar_{operation_str}_{start_str}_{end_str}.tif"
                output_file = os.path.join(output_folder, output_filename)
                
                feedback.pushInfo(f"\nProcesando intervalo {idx+1}/{total_intervals}: "
                                 f"{local_start.strftime('%Y-%m-%d %H:%M')} - "
                                 f"{local_end.strftime('%Y-%m-%d %H:%M')} (hora local)")
                feedback.pushInfo(f"Archivos en este intervalo: {len(interval_files_list)}")
                
                if not interval_files_list:
                    feedback.pushInfo("No hay archivos en este intervalo. Saltando...")
                    continue
                
                try:
                    # Leer el primer archivo para obtener metadatos
                    with rasterio.open(interval_files_list[0]) as src:
                        profile = src.profile.copy()
                        shape = src.shape
                        transform = src.transform
                        crs = src.crs
                    
                    # Inicializar matrices según la operación
                    if operation_idx == 0:  # Suma
                        accumulated = np.zeros(shape, dtype=np.float32)
                    elif operation_idx == 1:  # Media
                        accumulated = np.zeros(shape, dtype=np.float32)
                        sample_count = np.zeros(shape, dtype=np.int16)
                    elif operation_idx == 2:  # Máximo
                        accumulated = np.full(shape, -np.inf, dtype=np.float32)
                    elif operation_idx == 3:  # Mínimo
                        accumulated = np.full(shape, np.inf, dtype=np.float32)
                    
                    # Procesar cada archivo en el intervalo
                    valid_files = 0
                    
                    for file_path in interval_files_list:
                        try:
                            # Leer el archivo GeoTIFF
                            with rasterio.open(file_path) as src:
                                data = src.read(1)
                                
                                # Verificar que los datos tengan las dimensiones esperadas
                                if data.shape != shape:
                                    feedback.pushWarning(f"Error: Dimensiones incorrectas en {os.path.basename(file_path)}. "
                                                      f"Esperado {shape}, recibido {data.shape}. Saltando archivo...")
                                    continue
                                
                                # Aplicar umbral para operaciones estadísticas
                                valid_mask = data >= nodata_threshold
                                
                                # Actualizar según la operación
                                if operation_idx == 0:  # Suma
                                    # Para suma, solo sumamos valores por encima del umbral
                                    data_masked = data.copy()
                                    data_masked[~valid_mask] = 0
                                    accumulated += data_masked
                                
                                elif operation_idx == 1:  # Media
                                    # Para media, acumulamos y contamos píxeles válidos
                                    data_masked = data.copy()
                                    data_masked[~valid_mask] = 0
                                    accumulated += data_masked
                                    sample_count += valid_mask.astype(np.int16)
                                
                                elif operation_idx == 2:  # Máximo
                                    # Para máximo, solo consideramos píxeles válidos
                                    np.maximum.at(accumulated, np.where(valid_mask), data[valid_mask])
                                
                                elif operation_idx == 3:  # Mínimo
                                    # Para mínimo, solo consideramos píxeles válidos
                                    np.minimum.at(accumulated, np.where(valid_mask), data[valid_mask])
                            
                            valid_files += 1
                            
                        except Exception as e:
                            feedback.pushWarning(f"Error al leer {os.path.basename(file_path)}: {str(e)}")
                            continue
                    
                    # Si no hay archivos válidos, pasar al siguiente intervalo
                    if valid_files == 0:
                        feedback.pushWarning(f"No se procesaron archivos válidos en este intervalo. Saltando...")
                        continue
                    
                    # Calcular resultado final
                    if operation_idx == 1:  # Media
                        # Reemplazar divisiones por cero con cero
                        with np.errstate(divide='ignore', invalid='ignore'):
                            result = np.divide(accumulated, sample_count, 
                                             out=np.zeros_like(accumulated), 
                                             where=sample_count>0)
                    else:
                        # Para suma, máximo y mínimo, usar acumulado directamente
                        result = accumulated
                        
                        # Convertir -inf/inf a nodata específicos para máx/mín
                        if operation_idx == 2:  # Máximo
                            result[result == -np.inf] = 0  # Usar 0 en lugar de NaN para mayor compatibilidad
                        
                        if operation_idx == 3:  # Mínimo
                            result[result == np.inf] = 0  # Usar 0 en lugar de NaN para mayor compatibilidad
                    
                    # Actualizar perfil para el archivo de salida
                    profile.update(
                        dtype=np.float32,
                        count=1,
                        nodata=None  # No establecer NoData explícitamente
                    )
                    
                    # Guardar resultado
                    with rasterio.open(output_file, 'w', **profile) as dst:
                        dst.write(result.astype(np.float32), 1)
                    
                    # Agregar a la lista de resultados
                    result_files.append(output_file)
                    feedback.pushInfo(f"Resultado guardado en: {output_filename}")
                    
                except Exception as e:
                    feedback.reportError(f"Error al procesar el intervalo: {str(e)}")
                    import traceback
                    feedback.reportError(traceback.format_exc())
                    continue
            
            # Mostrar resumen final
            if result_files:
                feedback.pushInfo(f"\nProcesamiento completado. Se generaron {len(result_files)} archivos de resultado.")
                feedback.pushInfo(f"Ubicación de los resultados: {output_folder}")
                # No cargamos las capas automáticamente, dejamos que el usuario las cargue si lo desea
            else:
                feedback.reportError("No se generaron archivos de salida.")
            
        except Exception as e:
            feedback.reportError(f"Error en el procesamiento: {str(e)}")
            import traceback
            feedback.reportError(traceback.format_exc())
            raise QgsProcessingException(str(e))
        
        return {self.OUTPUT_FOLDER: output_folder}
    
    def name(self):
        return 'radartimeseries'
        
    def displayName(self):
        return self.tr('Radar Series Temporales')
        
    def group(self):
        return self.tr('Radar Meteorológico')
        
    def groupId(self):
        return 'radarmeteo'
        
    def shortHelpString(self):
        return self.tr('Analiza archivos NetCDF de radar meteorológico en series temporales. '
                     'Permite seleccionar un rango de fechas, especificar un intervalo, '
                     'y aplicar operaciones estadísticas (suma, media, máximo, mínimo). '
                     'Genera múltiples archivos GeoTIFF en la carpeta de salida, '
                     'uno por cada intervalo de tiempo. '
                     'Departamento de Ingeniería Civil - UTPL')
        
    def tr(self, string):
        return QCoreApplication.translate('Processing', string)
        
    def createInstance(self):
        return NetCDFTimeSeriesAlgorithm()