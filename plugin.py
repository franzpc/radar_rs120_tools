# -*- coding: utf-8 -*-
import os.path

from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMenu

from qgis.core import QgsApplication
import processing

from .netcdf_to_geotiff_algorithm import NetCDFToGeoTIFFAlgorithm
from .netcdf_to_gif_algorithm import NetCDFToGIFAlgorithm
from .netcdf_time_series_algorithm import NetCDFTimeSeriesAlgorithm
from .radar_calibration_algorithm import RadarCalibrationAlgorithm
from .about_dialog import AboutDialog

# Almacenamos los algoritmos globalmente para accederlos sin necesidad de proveedor
GEOTIFF_ALGORITHM = NetCDFToGeoTIFFAlgorithm()
GIF_ALGORITHM = NetCDFToGIFAlgorithm()
TIME_SERIES_ALGORITHM = NetCDFTimeSeriesAlgorithm()
CALIBRATION_ALGORITHM = RadarCalibrationAlgorithm()

class NetCDFToGeoTIFFPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(self.plugin_dir, 'i18n', 'RadaresUTPL_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        self.actions = []
        self.menu = '&Radar RS120'  # Sin usar tr() aquí

    def initGui(self):
        # Acción para convertir a GeoTIFF
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        self.action_geotiff = QAction(QIcon(icon_path), 'Radar RS120 to GeoTIFF', self.iface.mainWindow())
        self.action_geotiff.triggered.connect(self.run_geotiff)
        self.iface.addPluginToMenu(self.menu, self.action_geotiff)
        self.actions.append(self.action_geotiff)
        
        # Acción para convertir a GIF
        self.action_gif = QAction(QIcon(icon_path), 'Radar RS120 to GIF', self.iface.mainWindow())
        self.action_gif.triggered.connect(self.run_gif)
        self.iface.addPluginToMenu(self.menu, self.action_gif)
        self.actions.append(self.action_gif)
        
        # Acción para Series Temporales
        self.action_time_series = QAction(QIcon(icon_path), 'Radar Series Temporales', self.iface.mainWindow())
        self.action_time_series.triggered.connect(self.run_time_series)
        self.iface.addPluginToMenu(self.menu, self.action_time_series)
        self.actions.append(self.action_time_series)
        
        # Nueva acción para Calibración de Radar
        self.action_calibration = QAction(QIcon(icon_path), 'Radar - Calibración a Precipitación', self.iface.mainWindow())
        self.action_calibration.triggered.connect(self.run_calibration)
        self.iface.addPluginToMenu(self.menu, self.action_calibration)
        self.actions.append(self.action_calibration)
        
        # Acción para mostrar información "Acerca de"
        self.action_about = QAction(QIcon(icon_path), 'Acerca', self.iface.mainWindow())
        self.action_about.triggered.connect(self.show_about)
        self.iface.addPluginToMenu(self.menu, self.action_about)
        self.actions.append(self.action_about)
        
    def tr(self, string):
        """Método para traducir textos"""
        return QCoreApplication.translate('NetCDFToGeoTIFFPlugin', string)

    def unload(self):
        # Quitar acciones del menú de complementos
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)

    def run_geotiff(self):
        # Ejecutar el algoritmo de GeoTIFF directamente
        processing.execAlgorithmDialog(GEOTIFF_ALGORITHM, {})
        
    def run_gif(self):
        # Ejecutar el algoritmo de GIF directamente
        processing.execAlgorithmDialog(GIF_ALGORITHM, {})
        
    def run_time_series(self):
        # Ejecutar el algoritmo de Series Temporales
        processing.execAlgorithmDialog(TIME_SERIES_ALGORITHM, {})
    
    def run_calibration(self):
        # Ejecutar el algoritmo de Calibración de Radar
        processing.execAlgorithmDialog(CALIBRATION_ALGORITHM, {})
        
    def show_about(self):
        # Mostrar el diálogo "Acerca de"
        dlg = AboutDialog()
        dlg.exec_()