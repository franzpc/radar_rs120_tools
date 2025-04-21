# -*- coding: utf-8 -*-
"""
/***************************************************************************
 NetCDFToGeoTIFF
                                 A QGIS plugin
 Convierte archivos NetCDF a GeoTIFF y los reproyecta a WGS84 Zona 17S
                             -------------------
        begin                : 2025-04-11
        copyright            : (C) 2025 by Franz Pucha Cofrep - UTPL
        email                : fapucha@utpl.edu.ec
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

# noinspection PyPep8Naming
def classFactory(iface):
    """Carga el plugin NetCDFToGeoTIFF.
    
    :param iface: Una instancia de la interfaz de QGIS.
    :type iface: QgsInterface
    """
    from .plugin import NetCDFToGeoTIFFPlugin
    return NetCDFToGeoTIFFPlugin(iface)