# -*- coding: utf-8 -*-
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (QgsProcessing,
                       QgsProcessingAlgorithm,
                       QgsProcessingParameterRasterLayer,
                       QgsProcessingParameterVectorLayer,
                       QgsProcessingParameterField,
                       QgsProcessingParameterFileDestination,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterNumber,
                       QgsProcessingException,
                       QgsRasterLayer,
                       QgsVectorLayer,
                       QgsProject)
import processing
import os
import tempfile
import gc
import numpy as np
from osgeo import gdal
from scipy.interpolate import griddata
from scipy import ndimage

# Habilitar excepciones para GDAL
gdal.UseExceptions()

class RadarCalibrationAlgorithm(QgsProcessingAlgorithm):
    """
    Algoritmo para calibrar datos de reflectividad de radar meteorológico (dBZ) a 
    valores de precipitación (mm) utilizando estaciones meteorológicas.
    """
    
    # Definición de parámetros
    RADAR_INPUT = 'RADAR_INPUT'
    DEM_INPUT = 'DEM_INPUT'
    STATIONS_INPUT = 'STATIONS_INPUT'
    ELEVATION_FIELD = 'ELEVATION_FIELD'
    PRECIPITATION_FIELD = 'PRECIPITATION_FIELD'
    INTERPOLATION_METHOD = 'INTERPOLATION_METHOD'
    NODATA_VALUE = 'NODATA_VALUE'
    OUTPUT = 'OUTPUT'
    
    def initAlgorithm(self, config=None):
        # Parámetros de entrada
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.RADAR_INPUT,
                self.tr('Imagen de radar (reflectividad dBZ)'),
                None,
                False
            )
        )
        
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.DEM_INPUT,
                self.tr('Modelo Digital de Elevación (DEM)'),
                None,
                False
            )
        )
        
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.STATIONS_INPUT,
                self.tr('Capa de estaciones meteorológicas'),
                [QgsProcessing.TypeVectorPoint],
                False
            )
        )
        
        self.addParameter(
            QgsProcessingParameterField(
                self.ELEVATION_FIELD,
                self.tr('Campo de elevación'),
                None,
                self.STATIONS_INPUT,
                QgsProcessingParameterField.Numeric,
                False
            )
        )
        
        self.addParameter(
            QgsProcessingParameterField(
                self.PRECIPITATION_FIELD,
                self.tr('Campo de precipitación (mm)'),
                None,
                self.STATIONS_INPUT,
                QgsProcessingParameterField.Numeric,
                False
            )
        )
        
        self.addParameter(
            QgsProcessingParameterEnum(
                self.INTERPOLATION_METHOD,
                self.tr('Método de interpolación'),
                options=['Linear', 'Cubic', 'Nearest'],
                defaultValue=0,
                optional=False
            )
        )
        
        self.addParameter(
            QgsProcessingParameterNumber(
                self.NODATA_VALUE,
                self.tr('Valor NoData para precipitación'),
                type=QgsProcessingParameterNumber.Double,
                defaultValue=-9999,
                optional=True
            )
        )
        
        # Parámetro de salida
        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT,
                self.tr('Precipitación calibrada (mm)'),
                fileFilter='GeoTIFF Files (*.tif *.tiff)',
                optional=False
            )
        )
    
    def calculateStatistics(self, raster_path, feedback, band=1):
        """Método para calcular estadísticas de un ráster"""
        try:
            ds = gdal.Open(raster_path)
            band_obj = ds.GetRasterBand(band)
            
            # Forzar cálculo de estadísticas
            stats = band_obj.GetStatistics(0, 1)  # 0=aproximado, 1=forzar
            min_val = stats[0]
            max_val = stats[1]
            mean = stats[2]
            stddev = stats[3]
            
            # Cerrar dataset y liberar memoria
            ds = None
            gc.collect()
            
            return min_val, max_val, mean, stddev
        except Exception as e:
            feedback.pushWarning(f"Error al calcular estadísticas con GetStatistics: {str(e)}")
            
            # Método alternativo usando NumPy
            try:
                ds = gdal.Open(raster_path)
                band_obj = ds.GetRasterBand(band)
                data = band_obj.ReadAsArray()
                nodata = band_obj.GetNoDataValue()
                
                # Crear máscara para eliminar valores nodata
                if nodata is not None:
                    mask = (data != nodata)
                    if np.any(mask):
                        min_val = np.min(data[mask])
                        max_val = np.max(data[mask])
                        mean = np.mean(data[mask])
                        stddev = np.std(data[mask])
                    else:
                        min_val, max_val, mean, stddev = 0, 1, 0, 0
                else:
                    min_val = np.min(data)
                    max_val = np.max(data)
                    mean = np.mean(data)
                    stddev = np.std(data)
                
                # Cerrar dataset y liberar memoria
                ds = None
                data = None
                gc.collect()
                
                return min_val, max_val, mean, stddev
            except Exception as e2:
                feedback.pushWarning(f"Error al calcular estadísticas con NumPy: {str(e2)}")
                return 0, 1, 0, 0
    
    def interpolateWithScipy(self, stations_layer, field_name, output_path, dem_path, method='linear', feedback=None):
        """Método de interpolación usando SciPy directamente con el DEM como referencia"""
        
        try:
            # Obtener información del DEM para dimensiones y geotransformación
            dem_ds = gdal.Open(dem_path)
            width = dem_ds.RasterXSize
            height = dem_ds.RasterYSize
            geotransform = dem_ds.GetGeoTransform()
            projection = dem_ds.GetProjection()
            
            # Calcular extensión del DEM
            xmin = geotransform[0]
            ymax = geotransform[3]
            xmax = xmin + width * geotransform[1]
            ymin = ymax + height * geotransform[5]  # Geotransform[5] es negativo
            
            if feedback:
                feedback.pushInfo(f"DEM dimensiones: {width}x{height}")
                feedback.pushInfo(f"DEM extensión: {xmin}, {ymin} - {xmax}, {ymax}")
            
            # Obtener coordenadas y valores de las estaciones
            x_coords = []
            y_coords = []
            values = []
            
            # Recorrer features de la capa de estaciones
            for feature in stations_layer.getFeatures():
                geom = feature.geometry().asPoint()
                value = feature[field_name]
                
                # Solo agregar si hay valor
                if value is not None:
                    x_coords.append(geom.x())
                    y_coords.append(geom.y())
                    values.append(float(value))
            
            if len(values) < 3:
                if feedback:
                    feedback.pushWarning(f"No hay suficientes puntos para interpolar (mínimo 3, tiene {len(values)})")
                return False
            
            # Convertir a arrays de numpy
            x = np.array(x_coords)
            y = np.array(y_coords)
            z = np.array(values)
            
            if feedback:
                feedback.pushInfo(f"Creando grid {height}x{width} para interpolación con SciPy")
            
            # Crear grid de coordenadas usando las dimensiones exactas del DEM
            # Crear arrays de coordenadas para la interpolación
            x_grid = np.linspace(xmin, xmax, width)
            y_grid = np.linspace(ymax, ymin, height)  # y decrece (ymax a ymin)
            
            # Crear mesh grid 2D
            xx, yy = np.meshgrid(x_grid, y_grid)
            
            # Realizar interpolación
            if feedback:
                feedback.pushInfo(f"Interpolando usando método {method}...")
            
            # Puntos para interpolación
            points = np.column_stack((x, y))
            
            # Realizar la interpolación
            z_interpolated = griddata(points, z, (xx, yy), method=method, fill_value=np.nan)
            
            # Rellenar valores faltantes
            if np.any(np.isnan(z_interpolated)):
                if feedback:
                    feedback.pushInfo("Rellenando valores faltantes...")
                # Usar filtro gaussiano para suavizar y rellenar huecos
                z_interpolated = ndimage.gaussian_filter(np.nan_to_num(z_interpolated), sigma=1.5)
            
            # Crear GeoTIFF de salida
            driver = gdal.GetDriverByName('GTiff')
            out_ds = driver.Create(output_path, width, height, 1, gdal.GDT_Float32)
            
            # Configurar georreferenciación
            out_ds.SetGeoTransform(geotransform)
            out_ds.SetProjection(projection)
            
            # Escribir datos
            out_band = out_ds.GetRasterBand(1)
            out_band.WriteArray(z_interpolated)
            out_band.SetNoDataValue(-9999)
            
            # Calcular estadísticas y cerrar
            out_band.ComputeStatistics(False)
            out_ds = None
            
            # Liberar memoria
            z_interpolated = None
            dem_ds = None
            gc.collect()
            
            if feedback:
                feedback.pushInfo(f"Interpolación completada y guardada en {output_path}")
            
            return True
            
        except Exception as e:
            if feedback:
                feedback.pushWarning(f"Error en interpolación: {str(e)}")
            return False
    
    def processAlgorithm(self, parameters, context, feedback):
        # Obtener parámetros
        radar_layer = self.parameterAsRasterLayer(parameters, self.RADAR_INPUT, context)
        dem_layer = self.parameterAsRasterLayer(parameters, self.DEM_INPUT, context)
        stations_layer = self.parameterAsVectorLayer(parameters, self.STATIONS_INPUT, context)
        elevation_field = self.parameterAsString(parameters, self.ELEVATION_FIELD, context)
        precipitation_field = self.parameterAsString(parameters, self.PRECIPITATION_FIELD, context)
        interpolation_method_idx = self.parameterAsEnum(parameters, self.INTERPOLATION_METHOD, context)
        nodata_value = self.parameterAsDouble(parameters, self.NODATA_VALUE, context)
        output_file = self.parameterAsFileOutput(parameters, self.OUTPUT, context)
        
        # Mapear método de interpolación
        interpolation_methods = ['linear', 'cubic', 'nearest']
        interpolation_method = interpolation_methods[interpolation_method_idx]
        
        # Validar parámetros
        if not radar_layer.isValid():
            raise QgsProcessingException(self.tr("Capa de radar no válida"))
        
        if not dem_layer.isValid():
            raise QgsProcessingException(self.tr("Capa DEM no válida"))
        
        if stations_layer is None or not stations_layer.isValid():
            raise QgsProcessingException(self.tr("Capa de estaciones no válida"))
        
        # Crear carpeta temporal para archivos intermedios
        temp_dir = tempfile.mkdtemp()
        feedback.pushInfo(f"Carpeta temporal: {temp_dir}")
        
        # Diccionario para archivos temporales
        temp_files = {}
        
        try:
            # Obtener información del ráster de radar
            feedback.pushInfo("Obteniendo información básica de las capas...")
            
            radar_ds = gdal.Open(radar_layer.source())
            radar_geotransform = radar_ds.GetGeoTransform()
            radar_projection = radar_ds.GetProjection()
            radar_width = radar_ds.RasterXSize
            radar_height = radar_ds.RasterYSize
            radar_crs = radar_layer.crs().authid()
            
            # Cerrar dataset
            radar_ds = None
            gc.collect()

            # Extraer extensión del radar
            radar_extent = radar_layer.extent()
            xmin = radar_extent.xMinimum()
            xmax = radar_extent.xMaximum()
            ymin = radar_extent.yMinimum()
            ymax = radar_extent.yMaximum()
            
            # Calcular resolución del ráster de radar
            cell_size_x = radar_layer.rasterUnitsPerPixelX()
            cell_size_y = radar_layer.rasterUnitsPerPixelY()
            
            feedback.pushInfo(f"Radar: {radar_width}x{radar_height} pixeles, resolución: {cell_size_x}x{cell_size_y}")
            feedback.pushInfo(f"Extensión: ({xmin}, {ymin}) - ({xmax}, {ymax})")
            
            # Preparar extensión para algoritmos
            extent_string = f"{xmin},{xmax},{ymin},{ymax} [{radar_crs}]"
            
            # Verificar si las estaciones necesitan reproyección
            if stations_layer.crs().authid() != radar_crs:
                feedback.pushInfo("Reproyectando estaciones meteorológicas...")
                temp_files['stations_reprojected'] = os.path.join(temp_dir, "stations_reprojected.gpkg")
                
                processing.run("native:reprojectlayer", {
                    'INPUT': stations_layer,
                    'TARGET_CRS': radar_crs,
                    'OUTPUT': temp_files['stations_reprojected']
                }, context=context, feedback=feedback)
                
                # Actualizar la capa de estaciones
                stations_layer = QgsVectorLayer(temp_files['stations_reprojected'], "stations_reprojected", "ogr")
            
            # Alinear DEM con radar
            feedback.pushInfo("Alineando DEM con el ráster de radar...")
            temp_files['dem_aligned'] = os.path.join(temp_dir, "dem_aligned.tif")
            
            processing.run("gdal:warpreproject", {
                'INPUT': dem_layer,
                'SOURCE_CRS': dem_layer.crs().authid(),
                'TARGET_CRS': radar_crs,
                'RESAMPLING': 0,  # Vecino más cercano
                'TARGET_RESOLUTION': cell_size_x,
                'TARGET_EXTENT': extent_string,
                'TARGET_EXTENT_CRS': radar_crs,
                'NODATA': None,
                'OUTPUT': temp_files['dem_aligned']
            }, context=context, feedback=feedback)
            
            if feedback.isCanceled():
                return {self.OUTPUT: None}
                
            # 1. GENERACIÓN DE LA IMAGEN DE NORMALIZACIÓN
            feedback.pushInfo("\n1. GENERACIÓN DE LA IMAGEN DE NORMALIZACIÓN")
            feedback.setProgress(10)
            
            # 1.1 Interpolación de elevación de estaciones
            feedback.pushInfo("Interpolando elevaciones de estaciones...")
            temp_files['elevacion_estaciones'] = os.path.join(temp_dir, "elevacion_estaciones.tif")
            
            self.interpolateWithScipy(
                stations_layer, 
                elevation_field, 
                temp_files['elevacion_estaciones'],
                temp_files['dem_aligned'],
                method=interpolation_method,
                feedback=feedback
            )
            
            # 1.2 Calcular diferencia absoluta entre DEM y elevaciones interpoladas
            feedback.pushInfo("Calculando diferencia de altura...")
            temp_files['diferencia_altura'] = os.path.join(temp_dir, "diferencia_altura.tif")
            
            processing.run("gdal:rastercalculator", {
                'INPUT_A': temp_files['dem_aligned'],
                'BAND_A': 1,
                'INPUT_B': temp_files['elevacion_estaciones'],
                'BAND_B': 1,
                'FORMULA': 'abs(A-B)',
                'NO_DATA': nodata_value,
                'RTYPE': 5,  # Float32
                'OPTIONS': '',
                'EXTRA': '',
                'OUTPUT': temp_files['diferencia_altura']
            }, context=context, feedback=feedback)
            
            feedback.setProgress(30)
            
            # 1.3 Normalizar diferencia de altura
            feedback.pushInfo("Normalizando diferencia de altura...")
            
            # Obtener valor máximo con método seguro
            min_val, max_val_diferencia, mean, stddev = self.calculateStatistics(
                temp_files['diferencia_altura'],
                feedback
            )
            
            if max_val_diferencia <= 0:
                feedback.pushInfo("ADVERTENCIA: Valor máximo de diferencia es cero o negativo. Usando 1 como valor máximo.")
                max_val_diferencia = 1
            
            temp_files['normalizacion_altura'] = os.path.join(temp_dir, "normalizacion_altura.tif")
            
            processing.run("gdal:rastercalculator", {
                'INPUT_A': temp_files['diferencia_altura'],
                'BAND_A': 1,
                'FORMULA': f'A/{max_val_diferencia}',
                'NO_DATA': nodata_value,
                'RTYPE': 5,  # Float32
                'OPTIONS': '',
                'EXTRA': '',
                'OUTPUT': temp_files['normalizacion_altura']
            }, context=context, feedback=feedback)
            
            feedback.setProgress(40)
            
            # 1.4 Calcular distancias (Data Metrics)
            feedback.pushInfo("Calculando distancias a estaciones (Data Metrics)...")
            temp_files['data_metrics'] = os.path.join(temp_dir, "data_metrics.tif")
            
            processing.run("gdal:proximity", {
                'INPUT': temp_files['elevacion_estaciones'],
                'BAND': 1,
                'VALUES': '',
                'UNITS': 0,  # Píxeles
                'MAX_DISTANCE': 0,  # Sin límite
                'REPLACE': 0,
                'NODATA': 0,
                'OPTIONS': '',
                'DATA_TYPE': 5,  # Float32
                'OUTPUT': temp_files['data_metrics']
            }, context=context, feedback=feedback)
            
            if feedback.isCanceled():
                return {self.OUTPUT: None}
                
            feedback.setProgress(50)
            
            # 1.5 Normalizar Data Metrics
            feedback.pushInfo("Normalizando Data Metrics...")
            
            # Obtener valores máximo y mínimo
            min_val_metrics, max_val_metrics, mean, stddev = self.calculateStatistics(
                temp_files['data_metrics'],
                feedback
            )
            
            if max_val_metrics <= min_val_metrics:
                feedback.pushInfo("ADVERTENCIA: Valores max y min iguales en metrics. Ajustando valores.")
                max_val_metrics = min_val_metrics + 1
            
            temp_files['normalizacion_data_metrics'] = os.path.join(temp_dir, "normalizacion_data_metrics.tif")
            
            formula = f"(({max_val_metrics}/({max_val_metrics}+{min_val_metrics}))*(A+{min_val_metrics}))/{max_val_metrics}"
            
            processing.run("gdal:rastercalculator", {
                'INPUT_A': temp_files['data_metrics'],
                'BAND_A': 1,
                'FORMULA': formula,
                'NO_DATA': nodata_value,
                'RTYPE': 5,  # Float32
                'OPTIONS': '',
                'EXTRA': '',
                'OUTPUT': temp_files['normalizacion_data_metrics']
            }, context=context, feedback=feedback)
            
            feedback.setProgress(60)
            
            # 1.6 Generar peso de imagen (suma de normalizaciones)
            feedback.pushInfo("Generando peso de imagen...")
            temp_files['peso_imagen'] = os.path.join(temp_dir, "peso_imagen.tif")
            
            processing.run("gdal:rastercalculator", {
                'INPUT_A': temp_files['normalizacion_altura'],
                'BAND_A': 1,
                'INPUT_B': temp_files['normalizacion_data_metrics'],
                'BAND_B': 1,
                'FORMULA': 'A+B',
                'NO_DATA': nodata_value,
                'RTYPE': 5,  # Float32
                'OPTIONS': '',
                'EXTRA': '',
                'OUTPUT': temp_files['peso_imagen']
            }, context=context, feedback=feedback)
            
            if feedback.isCanceled():
                return {self.OUTPUT: None}
                
            feedback.setProgress(65)
            
            # 1.7 Normalización final del peso
            feedback.pushInfo("Normalizando peso de imagen...")
            
            # Obtener valores máximo y mínimo
            min_val_peso, max_val_peso, mean, stddev = self.calculateStatistics(
                temp_files['peso_imagen'],
                feedback
            )
            
            if max_val_peso <= min_val_peso:
                feedback.pushInfo("ADVERTENCIA: Valores max y min iguales en peso. Ajustando valores.")
                max_val_peso = min_val_peso + 1
            
            temp_files['normalizacion_peso_imagen'] = os.path.join(temp_dir, "normalizacion_peso_imagen.tif")
            
            formula = f"(({max_val_peso}/({max_val_peso}+{min_val_peso}))*(A+{min_val_peso}))/{max_val_peso}"
            
            processing.run("gdal:rastercalculator", {
                'INPUT_A': temp_files['peso_imagen'],
                'BAND_A': 1,
                'FORMULA': formula,
                'NO_DATA': nodata_value,
                'RTYPE': 5,  # Float32
                'OPTIONS': '',
                'EXTRA': '',
                'OUTPUT': temp_files['normalizacion_peso_imagen']
            }, context=context, feedback=feedback)
            
            feedback.setProgress(70)
            
            # 2. CALIBRACIÓN DE RADAR A PRECIPITACIÓN
            feedback.pushInfo("\n2. CALIBRACIÓN DE RADAR A PRECIPITACIÓN")
            
            # 2.1 Interpolación de precipitación de estaciones
            feedback.pushInfo("Interpolando precipitación de estaciones...")
            temp_files['p_estaciones'] = os.path.join(temp_dir, "p_estaciones.tif")
            
            self.interpolateWithScipy(
                stations_layer, 
                precipitation_field, 
                temp_files['p_estaciones'],
                temp_files['dem_aligned'],
                method=interpolation_method,
                feedback=feedback
            )
                
            feedback.setProgress(75)
            
            # 2.2 Extraer valores de radar y calcular relaciones
            feedback.pushInfo("Extrayendo valores de radar y calculando relaciones...")
            
            # Leer datos directamente
            radar_ds = gdal.Open(radar_layer.source())
            radar_band = radar_ds.GetRasterBand(1)
            radar_data = radar_band.ReadAsArray()
            radar_gt = radar_ds.GetGeoTransform()
            
            # Procesar cada estación y crear puntos con valores para interpolación
            points_x = []
            points_y = []
            relation_values = []
            
            for feature in stations_layer.getFeatures():
                geom = feature.geometry().asPoint()
                x = geom.x()
                y = geom.y()
                precip_val = feature[precipitation_field]
                
                # Convertir coordenadas a píxeles
                px = int((x - radar_gt[0]) / radar_gt[1])
                py = int((y - radar_gt[3]) / radar_gt[5])
                
                # Verificar si está dentro del ráster
                if 0 <= px < radar_ds.RasterXSize and 0 <= py < radar_ds.RasterYSize:
                    radar_val = float(radar_data[py, px])
                    
                    # Solo considerar puntos con precipitación positiva
                    if precip_val is not None and precip_val > 0:
                        relation = radar_val / precip_val
                        points_x.append(x)
                        points_y.append(y)
                        relation_values.append(relation)
                        
                        feedback.pushInfo(f"Estación en ({x}, {y}): Radar={radar_val}, Precipitación={precip_val}, Relación={relation}")
            
            # Liberar memoria
            radar_data = None
            radar_ds = None
            gc.collect()
            
            # 2.3 y 2.4 Interpolar relaciones
            feedback.pushInfo(f"Interpolando relaciones entre puntos ({len(points_x)} puntos)...")
            temp_files['mapa_relaciones'] = os.path.join(temp_dir, "mapa_relaciones.tif")
            
            # Verificar que hay suficientes puntos
            if len(points_x) < 3:
                feedback.pushWarning("No hay suficientes puntos con valores de relación. Usando valor constante 1.0")
                
                # Crear un raster constante basado en DEM
                dem_ds = gdal.Open(temp_files['dem_aligned'])
                width = dem_ds.RasterXSize
                height = dem_ds.RasterYSize
                gt = dem_ds.GetGeoTransform()
                projection = dem_ds.GetProjection()
                
                # Crear raster constante
                driver = gdal.GetDriverByName('GTiff')
                rel_ds = driver.Create(temp_files['mapa_relaciones'], width, height, 1, gdal.GDT_Float32)
                rel_ds.SetGeoTransform(gt)
                rel_ds.SetProjection(projection)
                
                # Llenar con 1.0 (valor neutro para división)
                rel_band = rel_ds.GetRasterBand(1)
                rel_band.Fill(1.0)
                rel_band.SetNoDataValue(nodata_value)
                
                # Cerrar dataset
                rel_ds = None
                dem_ds = None
            else:
                # Convertir a arrays de numpy
                points_x = np.array(points_x)
                points_y = np.array(points_y)
                relation_values = np.array(relation_values)
                
                # Interpolar usando SciPy
                # Obtener dimensiones del DEM
                dem_ds = gdal.Open(temp_files['dem_aligned'])
                width = dem_ds.RasterXSize
                height = dem_ds.RasterYSize
                gt = dem_ds.GetGeoTransform()
                projection = dem_ds.GetProjection()
                
                # Crear grid para interpolación
                x_coords = np.linspace(gt[0], gt[0] + width * gt[1], width)
                y_coords = np.linspace(gt[3], gt[3] + height * gt[5], height)
                xx, yy = np.meshgrid(x_coords, y_coords)
                
                # Realizar interpolación
                points = np.column_stack((points_x, points_y))
                grid_z = griddata(points, relation_values, (xx, yy), method=interpolation_method, fill_value=np.nan)
                
                # Rellenar valores NaN
                if np.any(np.isnan(grid_z)):
                    feedback.pushInfo("Rellenando valores faltantes en mapa de relaciones...")
                    grid_z = ndimage.gaussian_filter(np.nan_to_num(grid_z, nan=1.0), sigma=1.5)
                
                # Asegurar valores positivos (evitar divisiones por cero)
                grid_z = np.maximum(grid_z, 0.001)
                
                # Guardar como GeoTIFF
                driver = gdal.GetDriverByName('GTiff')
                rel_ds = driver.Create(temp_files['mapa_relaciones'], width, height, 1, gdal.GDT_Float32)
                rel_ds.SetGeoTransform(gt)
                rel_ds.SetProjection(projection)
                
                # Escribir datos
                rel_band = rel_ds.GetRasterBand(1)
                rel_band.WriteArray(grid_z)
                rel_band.SetNoDataValue(nodata_value)
                
                # Cerrar datasets
                rel_ds = None
                dem_ds = None
                
                # Liberar memoria
                grid_z = None
                xx = None
                yy = None
                gc.collect()
            
            feedback.setProgress(85)
            
            # 2.5 Calcular precipitación del radar (ConteoRadar / MapaRelaciones)
            feedback.pushInfo("Calculando precipitación del radar...")
            temp_files['p_radar'] = os.path.join(temp_dir, "p_radar.tif")
            
            # Usar calculadora raster con fórmula segura
            processing.run("gdal:rastercalculator", {
                'INPUT_A': radar_layer.source(),
                'BAND_A': 1,
                'INPUT_B': temp_files['mapa_relaciones'],
                'BAND_B': 1,
                'FORMULA': 'A / maximum(B, 0.001)',  # Evitar división por cero
                'NO_DATA': nodata_value,
                'RTYPE': 5,  # Float32
                'OPTIONS': '',
                'EXTRA': '',
                'OUTPUT': temp_files['p_radar']
            }, context=context, feedback=feedback)
            
            feedback.setProgress(90)
            
            # 2.6 Aplicar pesos
            feedback.pushInfo("Aplicando pesos a radar y estaciones...")
            
            # 2.6.1 Peso Radar = Pradar * NormalizacionPesoImagen
            temp_files['peso_radar'] = os.path.join(temp_dir, "peso_radar.tif")
            
            processing.run("gdal:rastercalculator", {
                'INPUT_A': temp_files['p_radar'],
                'BAND_A': 1,
                'INPUT_B': temp_files['normalizacion_peso_imagen'],
                'BAND_B': 1,
                'FORMULA': 'A*B',
                'NO_DATA': nodata_value,
                'RTYPE': 5,  # Float32
                'OPTIONS': '',
                'EXTRA': '',
                'OUTPUT': temp_files['peso_radar']
            }, context=context, feedback=feedback)
            
            # 2.6.2 Peso Estaciones = PEstaciones * (1 - NormalizacionPesoImagen)
            temp_files['peso_estaciones'] = os.path.join(temp_dir, "peso_estaciones.tif")
            
            processing.run("gdal:rastercalculator", {
                'INPUT_A': temp_files['p_estaciones'],
                'BAND_A': 1,
                'INPUT_B': temp_files['normalizacion_peso_imagen'],
                'BAND_B': 1,
                'FORMULA': 'A*(1-B)',
                'NO_DATA': nodata_value,
                'RTYPE': 5,  # Float32
                'OPTIONS': '',
                'EXTRA': '',
                'OUTPUT': temp_files['peso_estaciones']
            }, context=context, feedback=feedback)
            
            feedback.setProgress(95)
            
            # 2.7 Generar mapa final (PesoRadar + PesoEstaciones)
            feedback.pushInfo("Generando mapa final de precipitación...")
            
            processing.run("gdal:rastercalculator", {
                'INPUT_A': temp_files['peso_radar'],
                'BAND_A': 1,
                'INPUT_B': temp_files['peso_estaciones'],
                'BAND_B': 1,
                'FORMULA': 'A+B',
                'NO_DATA': nodata_value,
                'RTYPE': 5,  # Float32
                'OPTIONS': '',
                'EXTRA': '',
                'OUTPUT': output_file
            }, context=context, feedback=feedback)
            
            # Generar estadísticas para el archivo final
            try:
                ds = gdal.Open(output_file, gdal.GA_Update)
                band = ds.GetRasterBand(1)
                band.ComputeStatistics(False)
                ds = None
            except Exception as e:
                feedback.pushWarning(f"Error al calcular estadísticas finales: {str(e)}")
            
            # Cargar la capa resultante en el proyecto
            output_layer = QgsRasterLayer(output_file, os.path.basename(output_file))
            if output_layer.isValid():
                QgsProject.instance().addMapLayer(output_layer)
                feedback.pushInfo(f"Capa de precipitación calibrada cargada en el proyecto: {os.path.basename(output_file)}")
            else:
                feedback.pushWarning("No se pudo cargar la capa resultante en el proyecto")
            
            # Resumen del proceso
            feedback.pushInfo("\nRESUMEN DEL PROCESO DE CALIBRACIÓN:")
            feedback.pushInfo(f"- Radar procesado: {radar_layer.name()}")
            feedback.pushInfo(f"- DEM utilizado: {dem_layer.name()}")
            feedback.pushInfo(f"- Estaciones procesadas: {stations_layer.featureCount()}")
            feedback.pushInfo(f"- Método de interpolación: {interpolation_method}")
            feedback.pushInfo(f"- Resultado guardado en: {output_file}")
            feedback.pushInfo("\nProceso completado exitosamente")
            
            # Liberar memoria
            del temp_files
            gc.collect()
            
        except Exception as e:
            import traceback
            feedback.reportError(f"Error en el procesamiento: {str(e)}")
            feedback.reportError(traceback.format_exc())
            raise QgsProcessingException(str(e))
        
        return {self.OUTPUT: output_file}
    
    def name(self):
        return 'radarcalibration'
        
    def displayName(self):
        return self.tr('Radar - Calibración a Precipitación')
        
    def group(self):
        return self.tr('Radar Meteorológico')
        
    def groupId(self):
        return 'radarmeteo'
        
    def shortHelpString(self):
        return self.tr('Calibra datos de reflectividad de radar meteorológico a valores de precipitación '
                      'en milímetros utilizando registros de estaciones meteorológicas. '
                      'Implementa el método de calibración que combina datos del radar con '
                      'mediciones de estaciones, ponderando según la distancia y elevación. '
                      'Departamento de Ingeniería Civil - UTPL')
        
    def tr(self, string):
        return QCoreApplication.translate('Processing', string)
        
    def createInstance(self):
        return RadarCalibrationAlgorithm()