# Radar RS120 Tools

Plugin de QGIS que proporciona herramientas para procesar y visualizar datos del radar meteorológico RS120.

## Descripción

Este plugin convierte archivos NetCDF del radar meteorológico RS120 a diferentes formatos:

- **GeoTIFF**: Conversión a formato GeoTIFF con reproyección a WGS84 UTM Zona 17S (EPSG:32717)
- **GIF Animado**: Generación de animaciones a partir de series temporales de archivos NetCDF

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

## Instalación

### Requisitos previos

El plugin requiere las siguientes dependencias de Python:

```bash
pip install numpy xarray rasterio matplotlib pillow requests
```

Para una instalación completa de todas las dependencias, ejecuta:

```bash
pip install numpy xarray rasterio matplotlib pillow requests netCDF4 dask
```

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

## Solución de problemas

### Errores comunes

- **Error de reproyección**: El plugin intenta varios métodos de reproyección. Si todos fallan, se generará un archivo en coordenadas geográficas (WGS84).
- **Error al cargar archivos NetCDF**: Asegúrate de que los archivos tengan un formato compatible con el radar RS120.
- **Mapa base no disponible**: La descarga del mapa base requiere conexión a internet. Sin conexión, el plugin funcionará pero sin mapa base.

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
