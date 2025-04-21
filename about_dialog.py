# -*- coding: utf-8 -*-
import os

from qgis.PyQt import QtGui, QtWidgets
from qgis.PyQt.QtCore import QCoreApplication, Qt

class AboutDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        """Constructor."""
        super(AboutDialog, self).__init__(parent)
        # Configurar el diálogo
        self.setWindowTitle(self.tr("Acerca de Radar RS120"))
        self.resize(400, 300)
        
        # Crear el layout
        layout = QtWidgets.QVBoxLayout()
        
        # Añadir título
        title_label = QtWidgets.QLabel(self.tr("Radar RS120 Tools"))
        title_font = title_label.font()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)  # Cambio: Qt viene de QtCore, no de QtWidgets
        layout.addWidget(title_label)
        
        # Añadir versión
        version_label = QtWidgets.QLabel(self.tr("Versión 1.0"))
        version_label.setAlignment(Qt.AlignCenter)  # Cambio: Qt viene de QtCore, no de QtWidgets
        layout.addWidget(version_label)
        
        # Añadir espacio
        layout.addSpacing(20)
        
        # Añadir descripción
        description = self.tr(
            "Este plugin convierte archivos NetCDF del radar meteorológico RS120 "
            "a diferentes formatos, incluyendo GeoTIFF con reproyección a WGS84 "
            "Zona 17S (EPSG:32717) y GIF para visualización."
        )
        desc_label = QtWidgets.QLabel(description)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        
        # Añadir espacio
        layout.addSpacing(20)
        
        # Añadir autor
        author_label = QtWidgets.QLabel(self.tr("Departamento de Ingeniería Civil"))
        author_label.setAlignment(Qt.AlignCenter)  # Cambio: Qt viene de QtCore, no de QtWidgets
        layout.addWidget(author_label)
        
        # Añadir institución
        institution_label = QtWidgets.QLabel(self.tr("Universidad Técnica Particular de Loja"))
        institution_label.setAlignment(Qt.AlignCenter)  # Cambio: Qt viene de QtCore, no de QtWidgets
        layout.addWidget(institution_label)
        
        # Añadir nombre del desarrollador
        layout.addSpacing(10)
        dev_label = QtWidgets.QLabel(self.tr("desarrollado por @franzpc"))
        dev_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(dev_label)
        
        # Añadir espacio expansible
        layout.addStretch()
        
        # Añadir botón Cerrar
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # Establecer el layout
        self.setLayout(layout)
    
    def tr(self, string):
        return QCoreApplication.translate('AboutDialog', string)