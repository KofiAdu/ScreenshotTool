import os
import time
import csv
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtGui import QImage, QPainter
from qgis.PyQt.QtCore import QSize, QCoreApplication
from qgis.core import (
    QgsProject, QgsRectangle, QgsFeatureRequest,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsGeometry, QgsMapSettings, QgsMapRendererParallelJob,
    QgsPointXY
)

class ScreenshotTool:
    def __init__(self):
        self.output_dir = ""
        self.buffer_levels = []
        self.layer = None
        self.basemap_layer = None
        self.image_size = (512, 512)
        self.filter_expression = ""
        self.feature_limit = None
        self.save_metadata = False
        self.save_geometry = False
        self.metadata_rows = []

    def set_parameters(self, layer, basemap_layer, output_dir, buffer_levels,
                       filter_expression="", feature_limit=None,
                       save_metadata=False, save_geometry=False,
                       image_size=(512, 512)):
        self.layer = layer
        self.basemap_layer = basemap_layer
        self.output_dir = output_dir
        self.buffer_levels = buffer_levels
        self.image_size = image_size
        self.filter_expression = filter_expression
        self.feature_limit = feature_limit
        self.save_metadata = save_metadata
        self.save_geometry = save_geometry

    def get_filtered_features(self):
        if not self.layer:
            return []
        request = QgsFeatureRequest()
        if self.filter_expression:
            request.setFilterExpression(self.filter_expression)
        features = list(self.layer.getFeatures(request))
        if self.feature_limit:
            return features[:self.feature_limit]
        return features

    def transform_geometry(self, geom: QgsGeometry, crs_from, crs_to):
        transform = QgsCoordinateTransform(crs_from, crs_to, QgsProject.instance())
        g = QgsGeometry(geom)
        g.transform(transform)
        return g

    def bbox_around_geom(self, geom: QgsGeometry, buf_m: float, source_crs):
        webm_crs = QgsCoordinateReferenceSystem("EPSG:3857")
        g_transformed = self.transform_geometry(geom, source_crs, webm_crs)
        if g_transformed.type() == 0:
            pt = g_transformed.asPoint()
            return QgsRectangle(pt.x() - buf_m, pt.y() - buf_m, pt.x() + buf_m, pt.y() + buf_m)
        else:
            r = g_transformed.boundingBox()
            return QgsRectangle(r.xMinimum() - buf_m, r.yMinimum() - buf_m,
                                r.xMaximum() + buf_m, r.yMaximum() + buf_m)

    def render_patch(self, rect_3857: QgsRectangle, out_path: str):
        if not self.basemap_layer:
            print("[Error] No basemap layer provided.")
            return
        ms = QgsMapSettings()
        ms.setLayers([self.basemap_layer])
        ms.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        ms.setExtent(rect_3857)
        width, height = self.image_size
        ms.setOutputSize(QSize(width, height))

        img = QImage(width, height, QImage.Format_ARGB32)
        img.fill(0)
        painter = QPainter(img)
        job = QgsMapRendererParallelJob(ms)
        job.start(); job.waitForFinished()
        job.renderedImage().save(out_path, "PNG")
        painter.end()

    def extract_and_save_metadata(self, feature, src_crs):
        geom = feature.geometry()
        if not geom or geom.isEmpty():
            return

        # Representative point
        if geom.type() == 0:
            rep_pt_geom = geom
        elif geom.type() == 2:
            rep_pt_geom = geom.pointOnSurface()
        else:
            rep_pt_geom = geom.centroid()

        try:
            pt_src = rep_pt_geom.asPoint()
            to_wgs84 = QgsCoordinateTransform(src_crs, QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance())
            pt_wgs = to_wgs84.transform(QgsPointXY(pt_src))
            lon, lat = pt_wgs.x(), pt_wgs.y()

            attrs = feature.attributes()
            attr_names = [field.name() for field in self.layer.fields()]
            attr_data = {name: val for name, val in zip(attr_names, attrs)}

            row = {
                "feature_id": feature.id(),
                "lon": lon,
                "lat": lat,
                **attr_data
            }

            if self.save_geometry:
                row["geometry"] = geom.asWkt()

            self.metadata_rows.append(row)

        except Exception as e:
            print(f"Metadata error on feature {feature.id()}: {e}")

    def write_metadata_csv(self):
        if not self.metadata_rows:
            return
        csv_path = os.path.join(self.output_dir, "screenshot_metadata.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.metadata_rows[0].keys())
            writer.writeheader()
            writer.writerows(self.metadata_rows)

    def capture_screenshots(self):
        if not self.layer or not self.output_dir or not self.buffer_levels:
            QMessageBox.warning(None, "Missing Input", "Please ensure layer, output folder, and buffer levels are set.")
            return

        os.makedirs(self.output_dir, exist_ok=True)
        features = self.get_filtered_features()
        src_crs = self.layer.crs()

        for i, feature in enumerate(features):
            geom = feature.geometry()
            if not geom or geom.isEmpty():
                continue

            if self.save_metadata:
                self.extract_and_save_metadata(feature, src_crs)

            for buf_m in self.buffer_levels:
                rect = self.bbox_around_geom(geom, buf_m, src_crs)
                file_path = os.path.join(self.output_dir, f"feature_{feature.id()}_{buf_m}m.png")
                self.render_patch(rect, file_path)
                QCoreApplication.processEvents()
                time.sleep(0.3)

        if self.save_metadata:
            self.write_metadata_csv()

        QMessageBox.information(None, "Done", f"Saved screenshots for {len(features)} features.")
