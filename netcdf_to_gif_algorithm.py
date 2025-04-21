# -*- coding: utf-8 -*-
from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (QgsProcessing, QgsProcessingAlgorithm,
                       QgsProcessingParameterFile,
                       QgsProcessingParameterFileDestination,
                       QgsProcessingParameterString,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterBoolean,
                       QgsProcessingException)
import os
import xarray as xr
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import re
from PIL import Image
import tempfile
import shutil
import matplotlib.colors as mcolors
import urllib.request
import io
import math
import requests

class NetCDFToGIFAlgorithm(QgsProcessingAlgorithm):
    INPUT = 'INPUT'
    OUTPUT = 'OUTPUT'
    TITLE = 'TITLE'
    DURATION = 'DURATION'
    USE_BASEMAP = 'USE_BASEMAP'
    TRANSPARENCY_THRESHOLD = 'TRANSPARENCY_THRESHOLD'  # Parámetro para el umbral
    
    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT,
                self.tr('Directorio con archivos NetCDF'),
                behavior=QgsProcessingParameterFile.Folder,
                defaultValue=None
            )
        )
        
        self.addParameter(
            QgsProcessingParameterString(
                self.TITLE,
                self.tr('Título para el GIF'),
                defaultValue='Radar Meteorológico RS120'
            )
        )
        
        self.addParameter(
            QgsProcessingParameterNumber(
                self.DURATION,
                self.tr('Duración por frame (ms)'),
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=850,
                minValue=100,
                maxValue=5000
            )
        )
        
        # Parámetro para el umbral de transparencia
        self.addParameter(
            QgsProcessingParameterNumber(
                self.TRANSPARENCY_THRESHOLD,
                self.tr('Umbral de transparencia (dBZ)'),
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=30,  # Valor predeterminado 30
                minValue=0,
                maxValue=250
            )
        )
        
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.USE_BASEMAP,
                self.tr('Usar mapa base (OpenStreetMap)'),
                defaultValue=True
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT,
                self.tr('GIF de salida'),
                fileFilter='GIF Files (*.gif)',
                optional=True
            )
        )
    
    def processAlgorithm(self, parameters, context, feedback):
        input_folder = self.parameterAsFile(parameters, self.INPUT, context)
        output_gif = self.parameterAsFileOutput(parameters, self.OUTPUT, context)
        title = self.parameterAsString(parameters, self.TITLE, context)
        frame_duration = self.parameterAsInt(parameters, self.DURATION, context)
        use_basemap = self.parameterAsBool(parameters, self.USE_BASEMAP, context)
        # Obtener el valor del umbral de transparencia
        transparency_threshold = self.parameterAsInt(parameters, self.TRANSPARENCY_THRESHOLD, context)
        
        if not input_folder:
            raise QgsProcessingException(self.tr("No se ha seleccionado un directorio válido."))
            
        # Si no se especifica una salida, creamos un nombre basado en la entrada
        if not output_gif:
            output_gif = os.path.join(input_folder, "radar_animation.gif")
            
        feedback.pushInfo(f"Procesando directorio: {input_folder}")
        feedback.pushInfo(f"GIF de salida: {output_gif}")
        feedback.pushInfo(f"Título: {title}")
        feedback.pushInfo(f"Duración por frame: {frame_duration}ms")
        feedback.pushInfo(f"Usar mapa base: {'Sí' if use_basemap else 'No'}")
        feedback.pushInfo(f"Umbral de transparencia: {transparency_threshold} dBZ")
        
        # Crear un directorio temporal para los archivos PNG intermedios
        temp_png_folder = tempfile.mkdtemp()
        feedback.pushInfo(f"Directorio temporal para PNG: {temp_png_folder}")
        
        try:
            # Función para descargar mosaicos de OpenStreetMap directamente
            def download_osm_tiles(min_lon, max_lon, min_lat, max_lat, zoom=10):
                """
                Descarga mosaicos de OpenStreetMap para un área y zoom específicos.
                """
                def deg2num(lat_deg, lon_deg, zoom):
                    """Convierte coordenadas a números de mosaico"""
                    lat_rad = math.radians(lat_deg)
                    n = 2.0 ** zoom
                    xtile = int((lon_deg + 180.0) / 360.0 * n)
                    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
                    return (xtile, ytile)
                
                def num2deg(xtile, ytile, zoom):
                    """Convierte números de mosaico a coordenadas"""
                    n = 2.0 ** zoom
                    lon_deg = xtile / n * 360.0 - 180.0
                    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
                    lat_deg = math.degrees(lat_rad)
                    return (lon_deg, lat_deg)
                
                # Obtener los mosaicos necesarios
                x_min, y_max = deg2num(min_lat, min_lon, zoom)
                x_max, y_min = deg2num(max_lat, max_lon, zoom)
                
                # Limitar el número de mosaicos (no más de 6x6)
                if (x_max - x_min + 1) > 6:
                    center_x = (x_min + x_max) // 2
                    x_min = max(0, center_x - 3)
                    x_max = center_x + 3
                
                if (y_max - y_min + 1) > 6:
                    center_y = (y_min + y_max) // 2
                    y_min = max(0, center_y - 3)
                    y_max = center_y + 3
                
                feedback.pushInfo(f"Descargando mosaicos: zoom={zoom}, x={x_min}-{x_max}, y={y_min}-{y_max}")
                
                # Tamaño de mosaico (normalmente 256x256 píxeles)
                tile_size = 256
                
                # Crear imagen para contener todos los mosaicos
                width = (x_max - x_min + 1) * tile_size
                height = (y_max - y_min + 1) * tile_size
                map_img = Image.new('RGBA', (width, height))
                
                # URL base para OpenStreetMap
                url_template = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
                
                # Descargar e insertar cada mosaico
                total_tiles = (x_max - x_min + 1) * (y_max - y_min + 1)
                tiles_downloaded = 0
                
                for x in range(x_min, x_max + 1):
                    for y in range(y_min, y_max + 1):
                        url = url_template.replace('{z}', str(zoom)).replace('{x}', str(x)).replace('{y}', str(y))
                        
                        # Añadir User-Agent adecuado
                        headers = {
                            'User-Agent': 'QGIS_Plugin/1.0 (Radar_RS120_to_GIF; fapucha@utpl.edu.ec)'
                        }
                        
                        try:
                            response = requests.get(url, headers=headers, timeout=5)
                            if response.status_code == 200:
                                tile = Image.open(io.BytesIO(response.content))
                                map_img.paste(tile, ((x - x_min) * tile_size, (y - y_min) * tile_size))
                                tiles_downloaded += 1
                            else:
                                # Si falla, usar mosaico en blanco
                                blank = Image.new('RGBA', (tile_size, tile_size), (255, 255, 255, 0))
                                map_img.paste(blank, ((x - x_min) * tile_size, (y - y_min) * tile_size))
                        except Exception as e:
                            feedback.pushWarning(f"Error descargando mosaico {x},{y}: {str(e)}")
                            # Si falla, usar mosaico en blanco
                            blank = Image.new('RGBA', (tile_size, tile_size), (255, 255, 255, 0))
                            map_img.paste(blank, ((x - x_min) * tile_size, (y - y_min) * tile_size))
                
                feedback.pushInfo(f"Mosaicos descargados: {tiles_downloaded}/{total_tiles}")
                
                # Calcular las coordenadas exactas de la imagen resultante
                nw_lon, nw_lat = num2deg(x_min, y_min, zoom)
                se_lon, se_lat = num2deg(x_max + 1, y_max + 1, zoom)
                
                # Coordenadas reales del mapa descargado
                map_extent = (nw_lon, se_lon, se_lat, nw_lat)
                
                return map_img, map_extent
            
            # --- Definir la paleta de colores para reflectividad de radar (0-250 dBZ) ---
            rain_colors = [
                (0, 0, 0, 0),              # Transparente (valores <10 dBZ)
                (0.12, 0.56, 1, 0.7),      # Azul claro (lluvia ligera)
                (0.53, 0.81, 0.98, 0.8),   # Azul cielo (moderada)
                (0.2, 0.8, 0.2, 0.9),      # Verde (lluvia)
                (1, 1, 0, 0.9),            # Amarillo (fuerte)
                (1, 0.6, 0, 0.9),          # Naranja (muy fuerte)
                (1, 0, 0, 0.9)             # Rojo (extrema)
            ]
            
            # Crear colormap
            rain_cmap = plt.cm.colors.LinearSegmentedColormap.from_list("rain_cmap", rain_colors)
            
            # Normalización para valores de 0-250 dBZ (comenzando en 0, no en el umbral)
            norm = plt.cm.colors.Normalize(vmin=0, vmax=250)
            
            # Procesar archivos
            png_files = []
            nc_files = [f for f in sorted(os.listdir(input_folder)) if f.endswith('.nc4')]
            total_files = len(nc_files)
            
            if total_files == 0:
                feedback.pushWarning("No se encontraron archivos NetCDF (.nc4) en el directorio.")
                return {self.OUTPUT: None}
            
            feedback.pushInfo(f"Se encontraron {total_files} archivos NetCDF para procesar.")
            
            # Cargar y descargar el mapa base una sola vez (si se usa)
            base_map_image = None
            base_map_extent = None
            
            # Muestrear un archivo para obtener coordenadas
            if use_basemap and total_files > 0:
                try:
                    # Leer el primer archivo para obtener coordenadas
                    first_file = os.path.join(input_folder, nc_files[0])
                    ds = xr.open_dataset(first_file)
                    lons, lats = ds['lon'].values, ds['lat'].values
                    min_lon, max_lon = lons.min(), lons.max()
                    min_lat, max_lat = lats.min(), lats.max()
                    ds.close()
                    
                    feedback.pushInfo(f"Coordenadas para mapa base: LON {min_lon} a {max_lon}, LAT {min_lat} a {max_lat}")
                    
                    # Descargar mapa base
                    feedback.pushInfo("Descargando mapa base de OpenStreetMap...")
                    base_map_image, base_map_extent = download_osm_tiles(min_lon, max_lon, min_lat, max_lat, zoom=10)
                    
                    # Guardar mapa para verificación (opcional)
                    map_debug_path = os.path.join(temp_png_folder, "basemap_debug.png")
                    base_map_image.save(map_debug_path)
                    feedback.pushInfo(f"Mapa base guardado para depuración: {map_debug_path}")
                    feedback.pushInfo(f"Extensión del mapa base: {base_map_extent}")
                    
                except Exception as e:
                    feedback.pushWarning(f"Error al obtener mapa base: {str(e)}")
                    import traceback
                    feedback.pushWarning(traceback.format_exc())
                    use_basemap = False
            
            # --- Función de procesamiento basada en el código original ---
            def process_netcdf_file(file_path, output_path, radar_title, thresh):
                try:
                    # 1. Leer datos
                    ds = xr.open_dataset(file_path)
                    lons, lats = ds['lon'].values, ds['lat'].values
                    rain_data = ds['Band1'].values
                    
                    # 2. Crear máscara para valores menores al umbral de transparencia
                    mask = rain_data < thresh
                    rain_masked = np.ma.masked_array(rain_data, mask=mask)
                    
                    # Extraer detalles sobre los datos para depuración
                    min_lon, max_lon = lons.min(), lons.max()
                    min_lat, max_lat = lats.min(), lats.max()
                    feedback.pushInfo(f"Coordenadas: LON {min_lon} a {max_lon}, LAT {min_lat} a {max_lat}")
                    
                    # 3. Crear figura base con mapa
                    fig, ax = plt.subplots(figsize=(12, 10), dpi=150)
                    
                    # Configurar los límites para que coincidan con los datos
                    data_extent = [min_lon, max_lon, min_lat, max_lat]
                    ax.set_xlim(min_lon, max_lon)
                    ax.set_ylim(min_lat, max_lat)
                    
                    # Añadir mapa base si está disponible
                    if use_basemap and base_map_image is not None:
                        # Usar el mapa base descargado directamente
                        try:
                            # Convertir la imagen de PIL a un array de numpy para matplotlib
                            map_array = np.array(base_map_image)
                            
                            # Mostrar el mapa base con la extensión correcta (usando base_map_extent)
                            ax.imshow(map_array, extent=base_map_extent, alpha=0.7, aspect='auto')
                            feedback.pushInfo(f"Mapa base añadido a la imagen")
                        except Exception as e:
                            feedback.pushWarning(f"Error al mostrar mapa base: {str(e)}")
                    
                    # 4. Mostrar lluvia con la escala de colores comenzando en 0
                    rain_plot = ax.imshow(
                        rain_masked,
                        extent=data_extent,
                        cmap=rain_cmap,
                        norm=norm,  # Normalización desde 0 a 250
                        alpha=0.85,
                        interpolation='nearest',
                        origin='upper'  # Asegurar orientación correcta
                    )
                    
                    # Convertir coordenadas a grados, minutos, segundos para etiquetas
                    def decimal_to_dms(decimal, is_latitude=True):
                        direction = 'N' if decimal >= 0 and is_latitude else 'S' if is_latitude else 'E' if decimal >= 0 else 'W'
                        decimal = abs(decimal)
                        degrees = int(decimal)
                        minutes = int((decimal - degrees) * 60)
                        seconds = ((decimal - degrees) * 60 - minutes) * 60
                        return f"{degrees}°{minutes}'{seconds:.0f}\"{direction}"
                    
                    # Añadir etiquetas de coordenadas en los ejes
                    x_ticks = np.linspace(min_lon, max_lon, 5)
                    y_ticks = np.linspace(min_lat, max_lat, 5)
                    ax.set_xticks(x_ticks)
                    ax.set_yticks(y_ticks)
                    ax.set_xticklabels([decimal_to_dms(x, False) for x in x_ticks], fontsize=8)
                    ax.set_yticklabels([decimal_to_dms(y) for y in y_ticks], fontsize=8)
                    
                    # 5. Añadir barra de color con etiquetas personalizadas usando escala estándar
                    cbar = plt.colorbar(rain_plot, shrink=0.6)
                    cbar.set_label('Intensidad de lluvia (dBZ)')
                    
                    # Usar niveles fijos para la barra de colores (independiente del umbral)
                    tick_levels = [0, 10, 50, 90, 130, 170, 210, 250]
                    cbar.set_ticks(tick_levels)
                    
                    # Etiquetas estándar
                    tick_labels = [
                        '0\n(Sin lluvia)',
                        '10\n(Muy ligera)', 
                        '50\n(Ligera)', 
                        '90\n(Moderada)', 
                        '130\n(Fuerte)', 
                        '170\n(Muy fuerte)', 
                        '210\n(Extrema)',
                        '250\n(Torrencial)'
                    ]
                    cbar.set_ticklabels(tick_labels)
                    
                    # Añadir información sobre el umbral de transparencia en la leyenda
                    plt.figtext(0.5, 0.01, f"Umbral de transparencia: {thresh} dBZ", 
                             ha="center", fontsize=10, bbox={"facecolor":"white", "alpha":0.5, "pad":5})
                    
                    # 6. Añadir marca de tiempo
                    file_name = os.path.basename(file_path)
                    match = re.search(r'(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})', file_name)
                    if match:
                        year, month, day, hour, minute = map(int, match.groups())
                        utc_time = datetime(year, month, day, hour, minute)
                        ecuador_time = utc_time - timedelta(hours=5)
                        time_str = ecuador_time.strftime("%Y-%m-%d %H:%M (UTC-5)")
                        plt.title(f"{radar_title}\n{time_str}", fontsize=12, pad=20)
                    
                    # 7. Guardar imagen combinada
                    plt.savefig(output_path, bbox_inches='tight', pad_inches=0, dpi=150)
                    plt.close()
                    
                    # Cerrar el dataset
                    ds.close()
                    
                    return True
                    
                except Exception as e:
                    feedback.pushWarning(f"Error al procesar archivo {file_path}: {str(e)}")
                    import traceback
                    feedback.pushWarning(traceback.format_exc())
                    return False
            
            # --- Procesar cada archivo NetCDF ---
            for idx, file in enumerate(nc_files):
                if feedback.isCanceled():
                    break
                
                # Actualizar progreso
                feedback.setProgress(int((idx + 1) / total_files * 100))
                
                # Ruta del archivo y salida
                file_path = os.path.join(input_folder, file)
                output_path = os.path.join(temp_png_folder, f"frame_{idx:03d}.png")
                
                feedback.pushInfo(f"Procesando archivo: {file}")
                
                # Intentar procesar el archivo - pasando el umbral de transparencia
                if process_netcdf_file(file_path, output_path, title, transparency_threshold):
                    png_files.append(output_path)
                    feedback.pushInfo(f"✓ Imagen generada: frame_{idx:03d}.png")
            
            # --- Crear GIF animado ---
            if png_files:
                feedback.pushInfo(f"Generando GIF con {len(png_files)} imágenes...")
                
                # Ordenar los archivos para asegurar la secuencia correcta
                png_files = sorted(png_files)
                
                # Abrir todas las imágenes
                images = [Image.open(png) for png in png_files]
                
                # Guardar como GIF animado
                images[0].save(
                    output_gif,
                    save_all=True,
                    append_images=images[1:],
                    optimize=False,
                    duration=frame_duration,  # Duración por cada frame en milisegundos
                    loop=0  # 0 = infinito
                )
                
                feedback.pushInfo(f"GIF creado exitosamente: {output_gif}")
            else:
                feedback.pushWarning("No se generaron imágenes para el GIF")
        
        except Exception as e:
            feedback.reportError(f"Error en el procesamiento: {str(e)}")
            import traceback
            feedback.reportError(traceback.format_exc())
            raise QgsProcessingException(str(e))
        finally:
            # Limpiar archivos temporales
            try:
                shutil.rmtree(temp_png_folder)
                feedback.pushInfo("Archivos temporales eliminados")
            except Exception as e:
                feedback.pushWarning(f"No se pudieron eliminar todos los archivos temporales: {str(e)}")
        
        return {self.OUTPUT: output_gif}
        
    def name(self):
        return 'radartogif'
        
    def displayName(self):
        return self.tr('Radar RS120 to GIF')
        
    def group(self):
        return self.tr('Radar Meteorológico')
        
    def groupId(self):
        return 'radarmeteo'
        
    def shortHelpString(self):
        return self.tr('Crea un GIF animado a partir de archivos NetCDF de radar meteorológico con un mapa base de OpenStreetMap. Permite configurar el umbral de transparencia para visualizar mejor la lluvia, manteniendo la escala de colores completa. Departamento de Ingeniería Civil - UTPL')
        
    def tr(self, string):
        return QCoreApplication.translate('Processing', string)
        
    def createInstance(self):
        return NetCDFToGIFAlgorithm()