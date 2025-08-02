from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox, QAction
from qgis.core import QgsProject, QgsVectorLayer
from .screenshot_tool_dialog import ScreenshotToolDialog
from .screenshot_logic import ScreenshotTool  

class ScreenshotToolPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.dialog = None

    def initGui(self):
        self.action = QAction("Open Screenshot Tool", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu("&Screenshot Tool", self.action)

    def unload(self):
        self.iface.removePluginMenu("&Screenshot Tool", self.action)

    def run(self):
        if not self.dialog:
            self.dialog = ScreenshotToolDialog()

            # Fill layer dropdowns
            layers = list(QgsProject.instance().mapLayers().values())
            self.dialog.layerComboBox.clear()
            self.dialog.basemapComboBox.clear()
            for layer in layers:
                self.dialog.layerComboBox.addItem(layer.name())
                self.dialog.basemapComboBox.addItem(layer.name())

            # Browse button
            self.dialog.browseButton.clicked.connect(self.select_output_folder)

            # Run button
            self.dialog.runButton.clicked.connect(self.run_screenshot_tool)

        self.dialog.show()

    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self.dialog, "Select Output Folder")
        if folder:
            self.dialog.outputLineEdit.setText(folder)

    def run_screenshot_tool(self):
        try:
            # Inputs from UI
            vector_name = self.dialog.layerComboBox.currentText()
            basemap_name = self.dialog.basemapComboBox.currentText()
            vector_layer = QgsProject.instance().mapLayersByName(vector_name)[0]
            basemap_layer = QgsProject.instance().mapLayersByName(basemap_name)[0]

            if not isinstance(vector_layer, QgsVectorLayer):
                QMessageBox.critical(self.dialog, "Invalid Layer", "Please select a valid vector layer (not a raster).")
                return

            zoom_str = self.dialog.zoomLineEdit.text()
            zooms = [int(z.strip()) for z in zoom_str.split(",") if z.strip()]
            output = self.dialog.outputLineEdit.text()
            #filter_expr = self.dialog.filterLineEdit.text()
            
            def parse_simple_filter(user_input):
                 if not user_input:
                     return ""

                 conditions = []
                 parts = user_input.split(",")
                 for part in parts:
                        if "=" not in part:
                            continue
                        field, value = part.split("=", 1)
                        field = field.strip()
                        value = value.strip().lower()
                        conditions.append(f'lower(trim("{field}")) = \'{value}\'')
                 return " AND ".join(conditions)
                
            raw_filter = self.dialog.filterLineEdit.text()
            filter_expr = parse_simple_filter(raw_filter)

            limit = self.dialog.limitSpinBox.value()
            save_meta = self.dialog.metadataCheckBox.isChecked()
            save_geom = self.dialog.geometryCheckBox.isChecked()

            if not output or not zooms:
                QMessageBox.warning(self.dialog, "Missing Info", "Zoom levels and output folder are required.")
                return

            # Call screenshot tool
            tool = ScreenshotTool()
            tool.set_parameters(
                layer=vector_layer,
                basemap_layer=basemap_layer,
                output_dir=output,
                zoom_levels=zooms,
                filter_expression=filter_expr,
                feature_limit=limit if limit > 0 else None,
                save_metadata=save_meta,
                save_geometry=save_geom
            )
            tool.capture_screenshots()

        except Exception as e:
            QMessageBox.critical(self.dialog, "Error", str(e))
