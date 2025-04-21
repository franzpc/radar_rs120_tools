# -*- coding: utf-8 -*-
from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (QgsProcessing, QgsProcessingAlgorithm,
                       QgsProcessingParameterFile,
                       QgsProcessingParameterFileDestination,
                       QgsProcessingParameterNumber,
                       QgsProcessingException,
                       QgsProject, 
                       QgsRasterLayer,
                       QgsCoordinateReferenceSystem,
                       QgsColorRampShader,
                       QgsRasterShader,
                       QgsSingleBandPseudoColorRenderer)
from qgis.PyQt.QtGui import QColor
import processing
import os
import xarray as xr
import numpy as np
import rasterio
from rasterio.transform import from_origin
import subprocess

class NetCDFToGeoTIFFAlgorithm(QgsProcessingAlgorithm):
    INPUT = 'INPUT'
    OUTPUT = 'OUTPUT'
    NODATA_THRESHOLD = 'NODATA_THRESHOLD'  # Parámetro para el umbral
    
    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT,
                self.tr('Archivo NetCDF de entrada'),
                behavior=QgsProcessingParameterFile.File,
                fileFilter='NetCDF Files (*.nc *.nc4 *.cdf *.netcdf)',
                defaultValue=None
            )
        )
        
        # Parámetro para el umbral de NoData
        self.addParameter(
            QgsProcessingParameterNumber(
                self.NODATA_THRESHOLD,
                self.tr('Umbral para valores NoData (dBZ)'),
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=25,  # Valor predeterminado 25
                minValue=0,
                maxValue=250
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT,
                self.tr('GeoTIFF de salida'),
                fileFilter='GeoTIFF Files (*.tif *.tiff)',
                optional=True
            )
        )
    
    def processAlgorithm(self, parameters, context, feedback):
        input_nc = self.parameterAsFile(parameters, self.INPUT, context)
        output_tif = self.parameterAsFileOutput(parameters, self.OUTPUT, context)
        # Obtener el umbral de NoData
        nodata_threshold = self.parameterAsInt(parameters, self.NODATA_THRESHOLD, context)
        
        if not input_nc:
            raise QgsProcessingException(self.tr("No se ha seleccionado un archivo de entrada válido."))
        
        # Si no se especifica una salida, creamos un nombre basado en la entrada
        if not output_tif:
            base_name = os.path.splitext(os.path.basename(input_nc))[0]
            output_tif = os.path.join(os.path.dirname(input_nc), f"{base_name}.tif")
            
        feedback.pushInfo(f"Procesando archivo NetCDF: {input_nc}")
        feedback.pushInfo(f"GeoTIFF de salida: {output_tif}")
        feedback.pushInfo(f"Umbral para valores NoData: {nodata_threshold} dBZ")
        
        # Directorio y nombre del archivo temporal
        output_dir = os.path.dirname(output_tif)
        base_name = os.path.splitext(os.path.basename(output_tif))[0]
        temp_tif = os.path.join(output_dir, f"{base_name}_temp.tif")
        temp_vrt = os.path.join(output_dir, f"{base_name}_temp.vrt")
        
        try:
            # Abrir el NetCDF
            feedback.pushInfo("Abriendo archivo NetCDF...")
            ds = xr.open_dataset(input_nc)
            
            # Extraer datos de reflectividad (Band1), latitud y longitud
            feedback.pushInfo("Extrayendo datos de reflectividad, latitud y longitud...")
            reflectivity = ds['Band1'].values
            lats = ds['lat'].values
            lons = ds['lon'].values
            
            # Aplicar umbral para valores NoData
            feedback.pushInfo(f"Aplicando umbral de NoData ({nodata_threshold} dBZ)...")
            # Crear una copia para no modificar el original
            reflectivity_masked = reflectivity.copy()
            # Establecer valores por debajo del umbral como NaN (NoData)
            reflectivity_masked[reflectivity < nodata_threshold] = np.nan
            
            # Calcular resolución espacial (en grados)
            res_lon = abs(lons[1] - lons[0])
            res_lat = abs(lats[1] - lats[0])
            
            feedback.pushInfo(f"Resolución: lon={res_lon}, lat={res_lat}")
            
            # Definir la transformación geográfica (origen: esquina superior izquierda)
            transform = from_origin(
                lons.min(),  # Longitud mínima (oeste)
                lats.max(),  # Latitud máxima (norte)
                res_lon,     # Resolución en longitud
                res_lat      # Resolución en latitud
            )
            
            feedback.pushInfo("Creando GeoTIFF temporal...")
            
            # Crear el GeoTIFF temporal con coordenadas WGS84 (EPSG:4326)
            with rasterio.open(
                temp_tif,
                'w',
                driver='GTiff',
                height=reflectivity_masked.shape[0],
                width=reflectivity_masked.shape[1],
                count=1,
                dtype=reflectivity_masked.dtype,
                crs='+proj=longlat +datum=WGS84 +no_defs',  # WGS84 como string proj4
                transform=transform,
                nodata=np.nan
            ) as dst:
                dst.write(reflectivity_masked, 1)
            
            feedback.pushInfo(f"GeoTIFF temporal generado: {temp_tif}")
            
            # Intentamos varios métodos para la reproyección
            reproyeccion_exitosa = False
            
            # Método 1: GDAL desde la línea de comandos (el más confiable)
            try:
                feedback.pushInfo("Intentando reproyección con GDAL desde línea de comandos...")
                # Construir comando para gdal_warp
                gdal_warp_cmd = [
                    'gdalwarp',
                    '-t_srs', 'EPSG:32717',  # WGS84 UTM Zona 17S
                    '-r', 'near',            # Vecino más cercano
                    '-of', 'GTiff',
                    '-overwrite',
                    temp_tif,
                    output_tif
                ]
                
                # Ejecutar comando
                result = subprocess.run(gdal_warp_cmd, 
                                      capture_output=True, 
                                      text=True)
                
                if result.returncode == 0:
                    feedback.pushInfo("Reproyección exitosa usando GDAL desde línea de comandos")
                    reproyeccion_exitosa = True
                else:
                    feedback.pushInfo(f"Error al usar GDAL desde línea de comandos: {result.stderr}")
            except Exception as e:
                feedback.pushInfo(f"Error al intentar reproyectar con GDAL: {str(e)}")
            
            # Método 2: Usar el procesamiento de QGIS si el método 1 falló
            if not reproyeccion_exitosa:
                try:
                    feedback.pushInfo("Intentando reproyección con qgis:warpreproject...")
                    # Intentamos con definición de SRC explícita para evitar problemas de PROJ
                    utm_17s_wkt = 'PROJCS["WGS 84 / UTM zone 17S",GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",-81],PARAMETER["scale_factor",0.9996],PARAMETER["false_easting",500000],PARAMETER["false_northing",10000000],UNIT["metre",1]]'
                    
                    params = {
                        'INPUT': temp_tif,
                        'SOURCE_CRS': '+proj=longlat +datum=WGS84 +no_defs',
                        'TARGET_CRS': utm_17s_wkt,
                        'RESAMPLING': 0,  # Vecino más cercano
                        'OUTPUT': output_tif
                    }
                    
                    processing.run("gdal:warpreproject", params, context=context, feedback=feedback)
                    feedback.pushInfo("Reproyección exitosa usando qgis:warpreproject")
                    reproyeccion_exitosa = True
                except Exception as e:
                    feedback.pushInfo(f"Error al reproyectar con qgis:warpreproject: {str(e)}")
            
            # Método 3: Usar un enfoque diferente si los anteriores fallaron
            if not reproyeccion_exitosa:
                try:
                    feedback.pushInfo("Intentando reproyección con gdal:translate y gdal:assignprojection...")
                    
                    # Creamos un archivo temporal intermedio
                    temp_tif2 = os.path.join(output_dir, f"{base_name}_temp2.tif")
                    
                    # Primero copiamos el archivo con gdal:translate
                    translate_params = {
                        'INPUT': temp_tif,
                        'TARGET_CRS': None,
                        'NODATA': None,
                        'COPY_SUBDATASETS': False,
                        'OPTIONS': '',
                        'OUTPUT': temp_tif2
                    }
                    
                    processing.run("gdal:translate", translate_params, context=context, feedback=feedback)
                    
                    # Luego asignamos la proyección UTM 17S
                    proj_params = {
                        'INPUT': temp_tif2,
                        'CRS': 'EPSG:32717'
                    }
                    
                    processing.run("gdal:assignprojection", proj_params, context=context, feedback=feedback)
                    
                    # Finalmente hacemos la reproyección real
                    warp_params = {
                        'INPUT': temp_tif2,
                        'SOURCE_CRS': 'EPSG:4326',
                        'TARGET_CRS': 'EPSG:32717',
                        'RESAMPLING': 0,
                        'OUTPUT': output_tif
                    }
                    
                    processing.run("gdal:warpreproject", warp_params, context=context, feedback=feedback)
                    
                    # Limpiamos el archivo temporal extra
                    if os.path.exists(temp_tif2):
                        os.remove(temp_tif2)
                        
                    feedback.pushInfo("Reproyección exitosa usando el método de 3 pasos")
                    reproyeccion_exitosa = True
                except Exception as e:
                    feedback.pushInfo(f"Error con el método de 3 pasos: {str(e)}")
            
            # Si todos los métodos fallan, usamos la original pero advertimos al usuario
            if not reproyeccion_exitosa:
                import shutil
                feedback.pushInfo("ADVERTENCIA: Todos los métodos de reproyección fallaron")
                feedback.pushInfo("Generando archivo de salida en WGS84 (coordenadas geográficas)")
                shutil.copy(temp_tif, output_tif)
            
            # Verificamos que el archivo esté en UTM Zona 17S abriendo con rasterio
            try:
                with rasterio.open(output_tif) as src:
                    crs_wkt = src.crs.wkt
                    feedback.pushInfo(f"Proyección del archivo final: {src.crs}")
                    if "UTM zone 17S" in crs_wkt or "32717" in str(src.crs):
                        feedback.pushInfo("CONFIRMADO: El archivo está en WGS84 UTM Zona 17S")
                    else:
                        feedback.pushInfo("ADVERTENCIA: El archivo final NO está en WGS84 UTM Zona 17S")
            except Exception as e:
                feedback.pushInfo(f"No se pudo verificar la proyección final: {str(e)}")
            
            # Eliminar archivo temporal
            if os.path.exists(temp_tif):
                try:
                    os.remove(temp_tif)
                    feedback.pushInfo(f"Archivo temporal eliminado: {temp_tif}")
                except Exception as e:
                    feedback.pushInfo(f"No se pudo eliminar el archivo temporal: {str(e)}")
                
            feedback.pushInfo(f"GeoTIFF generado: {output_tif}")
            
            # Cargar la capa en QGIS
            if os.path.exists(output_tif):
                layer_name = os.path.basename(output_tif)
                raster_layer = QgsRasterLayer(output_tif, layer_name)
                
                if raster_layer.isValid():
                    # Forzar la CRS correcta al cargar
                    raster_layer.setCrs(QgsCoordinateReferenceSystem("EPSG:32717"))
                    
                    # Aplicar paleta de colores para lluvia (0-250)
                    self.apply_rain_color_ramp(raster_layer, nodata_threshold)
                    feedback.pushInfo("Paleta de colores de lluvia aplicada a la capa")
                    
                    # Añadir la capa al proyecto
                    QgsProject.instance().addMapLayer(raster_layer)
                    feedback.pushInfo(f"Capa '{layer_name}' cargada en QGIS")
                else:
                    feedback.reportError(f"Error al cargar la capa: {raster_layer.error().message()}")
            else:
                feedback.reportError(f"El archivo de salida no existe: {output_tif}")
            
            feedback.pushInfo("Procesamiento completado exitosamente")
            
        except Exception as e:
            feedback.reportError(f"Error en el procesamiento: {str(e)}")
            import traceback
            feedback.reportError(traceback.format_exc())
            raise QgsProcessingException(str(e))
        
        return {self.OUTPUT: output_tif}
    
    def apply_rain_color_ramp(self, raster_layer, threshold):
        """Aplica una paleta de colores para datos de lluvia/radar comenzando desde 0"""
        
        # Crear el objeto shader
        shader = QgsRasterShader()
        
        # Crear rampa de color
        color_ramp = QgsColorRampShader()
        color_ramp.setColorRampType(QgsColorRampShader.Interpolated)
        
        # Definir colores para diferentes rangos de valores (0-250)
        # Colores para lluvia, de más débil a más intensa, comenzando en 0
        color_list = [
            QgsColorRampShader.ColorRampItem(0, QColor(255, 255, 255, 0), 'Sin lluvia'),  # Transparente
            QgsColorRampShader.ColorRampItem(10, QColor(200, 255, 255), 'Muy débil'),     # Celeste muy claro
            QgsColorRampShader.ColorRampItem(25, QColor(150, 210, 255), 'Débil'),         # Celeste claro
            QgsColorRampShader.ColorRampItem(40, QColor(80, 170, 255), 'Ligera'),         # Celeste
            QgsColorRampShader.ColorRampItem(60, QColor(30, 110, 255), 'Moderada'),       # Azul claro
            QgsColorRampShader.ColorRampItem(80, QColor(0, 60, 225), 'Moderada-Fuerte'),  # Azul
            QgsColorRampShader.ColorRampItem(100, QColor(0, 150, 30), 'Fuerte'),          # Verde
            QgsColorRampShader.ColorRampItem(120, QColor(255, 255, 0), 'Muy fuerte'),     # Amarillo
            QgsColorRampShader.ColorRampItem(150, QColor(255, 150, 0), 'Intensa'),        # Naranja
            QgsColorRampShader.ColorRampItem(180, QColor(255, 0, 0), 'Muy intensa'),      # Rojo
            QgsColorRampShader.ColorRampItem(220, QColor(180, 0, 180), 'Extrema'),        # Púrpura
            QgsColorRampShader.ColorRampItem(250, QColor(128, 0, 128), 'Torrencial')      # Morado oscuro
        ]
        
        color_ramp.setColorRampItemList(color_list)
        
        # Configurar el shader
        shader.setRasterShaderFunction(color_ramp)
        
        # Crear el renderizador y aplicarlo a la capa
        renderer = QgsSingleBandPseudoColorRenderer(raster_layer.dataProvider(), 1, shader)
        raster_layer.setRenderer(renderer)
        
        # Configurar transparencia para valores bajos (sin lluvia)
        raster_layer.renderer().setOpacity(0.8)  # 80% de opacidad general
        
        # Actualizar la capa
        raster_layer.triggerRepaint()
        
    def name(self):
        return 'radartogeotiff'
        
    def displayName(self):
        return self.tr('Radar to GeoTIFF (WGS84 17S)')
        
    def group(self):
        return self.tr('Radar Meteorológico')
        
    def groupId(self):
        return 'radarmeteo'
        
    def shortHelpString(self):
        return self.tr('Convierte archivos NetCDF de radar meteorológico a GeoTIFF y los reproyecta a WGS84 Zona 17S (EPSG:32717). Permite establecer un umbral para valores NoData manteniendo la escala de colores completa. Departamento de Ingeniería Civil - UTPL')
        
    def tr(self, string):
        return QCoreApplication.translate('Processing', string)
        
    def createInstance(self):
        return NetCDFToGeoTIFFAlgorithm()