# Radar RS120 Tools

Plugin de QGIS que proporciona herramientas para procesar y visualizar datos del radar meteorológico RS120.

## Descripción

Este plugin convierte archivos NetCDF del radar meteorológico RS120 a diferentes formatos y ofrece funcionalidades para análisis de datos:

- **GeoTIFF**: Conversión a formato GeoTIFF con reproyección a WGS84 UTM Zona 17S (EPSG:32717)
- **GIF Animado**: Generación de animaciones a partir de series temporales de archivos NetCDF
- **Series Temporales**: Análisis de series temporales con operaciones estadísticas (suma, media, máximo, mínimo)
- **Calibración a Precipitación**: Calibra datos de reflectividad de radar a valores de precipitación (mm) usando estaciones meteorológicas

## Características principales

### Conversión a GeoTIFF

- Reproyección automática a WGS84 UTM Zona 17S (EPSG:32717)
- Umbral personalizable para valores NoData (por defecto 25 dBZ)
- Aplicación automática de paleta de colores para visualización de precipitación
- Carga automática de la capa resultante en QGIS

### Creación de GIF animado

- Umbral personalizable para transparencia (por defecto 30 dBZ)
- Incorporación opcional de mapa base de OpenStreetMap
- Velocidad de animación ajustable
- Título personalizable
- Procesamiento por lotes de directorios con múltiples archivos NetCDF

### Series Temporales

- Análisis de datos de radar en intervalos temporales definidos por el usuario
- Operaciones disponibles: suma, media, máximo y mínimo
- Ajuste automático de zona horaria (UTC a hora local)
- Umbral personalizable para valores NoData
- Generación de imágenes acumuladas o promedios para períodos específicos

### Calibración a Precipitación

- Integración de datos de estaciones meteorológicas con datos de radar
- Algoritmo de calibración basado en técnicas de interpolación espacial
- Consideración de efectos de elevación usando Modelos Digitales de Elevación (DEM)
- Generación de mapas de precipitación calibrados en milímetros (mm)
- Múltiples métodos de interpolación disponibles (lineal, cúbica, vecino más cercano)

## Instalación

### Requisitos previos

El plugin requiere las siguientes dependencias de Python:

```bash
pip install numpy xarray rasterio matplotlib pillow requests scipy pykrige
```

Para una instalación completa de todas las dependencias, ejecuta:

```bash
pip install numpy xarray rasterio matplotlib pillow requests scipy pykrige netCDF4 dask
```

Si alguna dependencia no está instalada, el plugin mostrará un mensaje indicando qué paquetes faltan y cómo instalarlos.

### Instalación del plugin

1. Descarga la última versión del plugin desde el repositorio
2. En QGIS, ve a "Complementos" > "Administrar e instalar complementos..."
3. Selecciona "Instalar a partir de ZIP"
4. Navega hasta el archivo ZIP descargado y selecciónalo
5. Haz clic en "Instalar complemento"

## Uso básico

### Conversión a GeoTIFF

1. En el menú principal de QGIS, selecciona "Radar RS120" > "Radar RS120 to GeoTIFF"
2. Selecciona el archivo NetCDF de entrada
3. Establece el umbral para valores NoData (opcional, predeterminado: 25 dBZ)
4. Selecciona la ubicación del archivo GeoTIFF de salida (opcional)
5. Haz clic en "Ejecutar"

### Creación de GIF animado

1. En el menú principal de QGIS, selecciona "Radar RS120" > "Radar RS120 to GIF"
2. Selecciona el directorio que contiene los archivos NetCDF
3. Personaliza el título para el GIF (opcional)
4. Ajusta la duración por frame (opcional, predeterminado: 850 ms)
5. Establece el umbral de transparencia (opcional, predeterminado: 30 dBZ)
6. Activa o desactiva el uso del mapa base (opcional, predeterminado: activado)
7. Selecciona la ubicación del archivo GIF de salida (opcional)
8. Haz clic en "Ejecutar"

### Series Temporales

1. En el menú principal de QGIS, selecciona "Radar RS120" > "Radar Series Temporales"
2. Selecciona la carpeta que contiene los archivos NetCDF
3. Define la fecha de inicio y fin para el análisis
4. Establece el intervalo en horas
5. Selecciona la operación estadística (suma, media, máximo, mínimo)
6. Ajusta el desplazamiento horario UTC (p.ej. -5 para Ecuador)
7. Define el umbral para valores NoData
8. Selecciona la carpeta de salida para los GeoTIFFs
9. Haz clic en "Ejecutar"

### Calibración a Precipitación

1. En el menú principal de QGIS, selecciona "Radar RS120" > "Radar - Calibración a Precipitación"
2. Selecciona la imagen de radar (reflectividad dBZ)
3. Selecciona el Modelo Digital de Elevación (DEM)
4. Selecciona la capa de estaciones meteorológicas
5. Indica el campo de elevación y el campo de precipitación
6. Selecciona el método de interpolación
7. Define el valor NoData para precipitación
8. Selecciona el archivo de salida para la precipitación calibrada
9. Haz clic en "Ejecutar"

## Solución de problemas

### Errores comunes

- **Error de reproyección**: El plugin intenta varios métodos de reproyección. Si todos fallan, se generará un archivo en coordenadas geográficas (WGS84).
- **Error al cargar archivos NetCDF**: Asegúrate de que los archivos tengan un formato compatible con el radar RS120.
- **Mapa base no disponible**: La descarga del mapa base requiere conexión a internet. Sin conexión, el plugin funcionará pero sin mapa base.
- **Dependencias faltantes**: Si falta alguna biblioteca Python, el plugin mostrará un mensaje con instrucciones para instalarlas.

### Compatibilidad

- El plugin ha sido probado en QGIS 3.16 y versiones posteriores
- Requiere Python 3.6 o superior

## Desarrollo

### Estructura del proyecto

```
radar_rs120_tools/
├── __init__.py
├── plugin.py
├── netcdf_to_geotiff_algorithm.py
├── netcdf_to_gif_algorithm.py
├── netcdf_time_series_algorithm.py
├── radar_calibration_algorithm.py
├── about_dialog.py
├── icon.png
├── metadata.txt
└── README.md
```

### Contribuciones

Las contribuciones son bienvenidas. Por favor, envía tus pull requests o reporta problemas en el repositorio del proyecto.

## Licencia

Este plugin está licenciado bajo la Licencia Pública General de GNU v2 o posterior.

## Autor

Departamento de Ingeniería Civil  
Universidad Técnica Particular de Loja  
@franzpc Franz Pucha Cofrep
