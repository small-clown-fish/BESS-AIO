from __future__ import annotations

import json
import csv
from collections import deque
from pathlib import Path
from typing import Any, Dict

from PySide6.QtCharts import QChart, QLineSeries
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem, QInputDialog
from PySide6.QtGui import QColor





class SiteMixin:
    def get_cluster_by_device(self, device_name: str):
        if not hasattr(self, "site"):
            return None

        for cluster in self.site.clusters:
            for dev in cluster.bms_devices:
                if dev.name == device_name:
                    return cluster

            for pcs in getattr(cluster, "pcs_devices", []):
                if pcs.name == device_name:
                    return cluster

        return None

    def refresh_site_view(self) -> None:
        if not hasattr(self, "site_cluster_table"):
            return

        self.site_name_label.setText(f"Site: {self.site.name}")
        if hasattr(self, "active_cluster_combo"):
            current = self.default_cluster.name if hasattr(self, "default_cluster") else ""

            self.active_cluster_combo.blockSignals(True)
            self.active_cluster_combo.clear()

            for cluster in self.site.clusters:
                self.active_cluster_combo.addItem(cluster.name)

            if current:
                self.active_cluster_combo.setCurrentText(current)

            self.active_cluster_combo.blockSignals(False)
        if hasattr(self, "cluster_binding_target_combo"):
            current = self.cluster_binding_target_combo.currentText()
            fallback = self.default_cluster.name if hasattr(self, "default_cluster") else ""

            self.cluster_binding_target_combo.blockSignals(True)
            self.cluster_binding_target_combo.clear()

            for cluster in self.site.clusters:
                self.cluster_binding_target_combo.addItem(cluster.name)

            if current:
                self.cluster_binding_target_combo.setCurrentText(current)
            elif fallback:
                self.cluster_binding_target_combo.setCurrentText(fallback)

            self.cluster_binding_target_combo.blockSignals(False)

        if hasattr(self, "move_bms_target_cluster_combo"):
            current = self.move_bms_target_cluster_combo.currentText()

            self.move_bms_target_cluster_combo.blockSignals(True)
            self.move_bms_target_cluster_combo.clear()

            for cluster in self.site.clusters:
                self.move_bms_target_cluster_combo.addItem(cluster.name)

            if current:
                self.move_bms_target_cluster_combo.setCurrentText(current)

            self.move_bms_target_cluster_combo.blockSignals(False)
        if hasattr(self, "cluster_dispatch_combo"):
            current = self.cluster_dispatch_combo.currentText()
            self.cluster_dispatch_combo.blockSignals(True)
            self.cluster_dispatch_combo.clear()
            for cluster in self.site.clusters:
                self.cluster_dispatch_combo.addItem(cluster.name)
            if current:
                self.cluster_dispatch_combo.setCurrentText(current)
            elif hasattr(self, "default_cluster"):
                self.cluster_dispatch_combo.setCurrentText(self.default_cluster.name)
            self.cluster_dispatch_combo.blockSignals(False)
        if hasattr(self, "cluster_pcs_combo"):
            current_pcs = self.default_cluster.pcs_device.name if self.default_cluster.pcs_device else self.current_pcs_name
            self.cluster_pcs_combo.blockSignals(True)
            self.cluster_pcs_combo.clear()
            for pcs_name in sorted(self.pcs_configs.keys()) or [self.current_pcs_name]:
                self.cluster_pcs_combo.addItem(pcs_name)
            self.cluster_pcs_combo.setCurrentText(current_pcs)
            self.cluster_pcs_combo.blockSignals(False)
        if hasattr(self, "site_name_edit"):
            self.site_name_edit.setText(self.site.name)
        if hasattr(self, "cluster_name_edit") and self.site.clusters:
            active = self.default_cluster if hasattr(self, "default_cluster") else self.site.clusters[0]
            self.cluster_name_edit.setText(active.name)
        self.site_cluster_table.setRowCount(0)

        for cluster in self.site.clusters:
            row = self.site_cluster_table.rowCount()
            self.site_cluster_table.insertRow(row)

            bms_names = ", ".join(dev.name for dev in cluster.bms_devices) or "-"
            pcs_name = ", ".join(pcs.name for pcs in getattr(cluster, "pcs_devices", [])) or "-"

            values = [
                cluster.name,
                bms_names,
                pcs_name,
                str(len(cluster.bms_devices)),
            ]

            for col, value in enumerate(values):
                self.site_cluster_table.setItem(row, col, QTableWidgetItem(value))

    def apply_cluster_name(self) -> None:
        if not hasattr(self, "cluster_name_edit"):
            return

        new_name = self.cluster_name_edit.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Warning", "Cluster name cannot be empty.")
            return

        if not hasattr(self, "default_cluster"):
            return

        old_name = self.default_cluster.name
        self.default_cluster.name = new_name

        self.log(f"[INFO] Cluster renamed: {old_name} -> {new_name}")

        self.save_site_config()
        self.refresh_site_view()
        self.refresh_overview()

    def apply_site_name(self) -> None:
        if not hasattr(self, "site_name_edit"):
            return

        new_name = self.site_name_edit.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Warning", "Site name cannot be empty.")
            return

        old_name = self.site.name
        self.site.name = new_name

        self.log(f"[INFO] Site renamed: {old_name} -> {new_name}")

        self.save_site_config()
        self.refresh_site_view()
        self.refresh_overview()

    def _get_selected_binding_cluster(self):
        """Return the cluster selected in the PCS Binding Cluster combo.

        Older versions always used self.default_cluster, which made every PCS
        bind to Cluster-1 after refresh. This helper makes the target explicit.
        """
        target_name = ""
        if hasattr(self, "cluster_binding_target_combo"):
            target_name = self.cluster_binding_target_combo.currentText().strip()
        if not target_name and hasattr(self, "active_cluster_combo"):
            target_name = self.active_cluster_combo.currentText().strip()
        if not target_name and hasattr(self, "default_cluster"):
            target_name = self.default_cluster.name

        for cluster in getattr(self.site, "clusters", []):
            if cluster.name == target_name:
                return cluster
        return getattr(self, "default_cluster", None)

    def apply_cluster_pcs_binding(self) -> None:
        if not hasattr(self, "cluster_pcs_combo"):
            return

        pcs_name = self.cluster_pcs_combo.currentText().strip()
        if not pcs_name:
            QMessageBox.warning(self, "Warning", "PCS name cannot be empty.")
            return

        target_cluster = self._get_selected_binding_cluster()
        if target_cluster is None:
            QMessageBox.warning(self, "Warning", "Please select a target cluster first.")
            return

        from ..models import Device

        pcs_dev = Device(
            name=pcs_name,
            device_type="PCS",
            config=self.get_pcs_config_by_name(pcs_name),
        )

        # A PCS should normally belong to one cluster. Remove it from other
        # clusters first to avoid duplicated dispatch targets.
        for cluster in self.site.clusters:
            if cluster is target_cluster:
                continue
            if hasattr(cluster, "pcs_devices"):
                cluster.pcs_devices = [p for p in cluster.pcs_devices if p.name != pcs_name]

        if not hasattr(target_cluster, "pcs_devices"):
            target_cluster.pcs_devices = []
        if not any(p.name == pcs_name for p in target_cluster.pcs_devices):
            target_cluster.pcs_devices.append(pcs_dev)
            self.log(f"[INFO] Added PCS to cluster: {target_cluster.name} -> {pcs_name}")
        else:
            self.log(f"[INFO] PCS already bound to cluster: {target_cluster.name} -> {pcs_name}")

        self.save_site_config()
        self.refresh_site_view()
        self.refresh_overview()

    def remove_cluster_pcs_binding(self) -> None:
        if not hasattr(self, "cluster_pcs_combo"):
            return
        pcs_name = self.cluster_pcs_combo.currentText().strip()
        target_cluster = self._get_selected_binding_cluster()
        if not pcs_name or target_cluster is None or not hasattr(target_cluster, "pcs_devices"):
            return
        before = len(target_cluster.pcs_devices)
        target_cluster.pcs_devices = [p for p in target_cluster.pcs_devices if p.name != pcs_name]
        if len(target_cluster.pcs_devices) != before:
            self.log(f"[INFO] Removed PCS from cluster: {target_cluster.name} -> {pcs_name}")
            self.save_site_config()
            self.refresh_site_view()
            self.refresh_overview()

    def on_active_cluster_changed(self, cluster_name: str) -> None:
        if not cluster_name:
            return

        for cluster in self.site.clusters:
            if cluster.name == cluster_name:
                self.default_cluster = cluster

                if hasattr(self, "cluster_name_edit"):
                    self.cluster_name_edit.setText(cluster.name)

                if hasattr(self, "cluster_binding_target_combo"):
                    self.cluster_binding_target_combo.setCurrentText(cluster.name)

                if hasattr(self, "cluster_pcs_combo"):
                    pcs_name = ""
                    if getattr(cluster, "pcs_devices", []):
                        pcs_name = cluster.pcs_devices[0].name
                    elif getattr(cluster, "pcs_device", None):
                        pcs_name = cluster.pcs_device.name
                    if pcs_name:
                        if self.cluster_pcs_combo.findText(pcs_name) < 0:
                            self.cluster_pcs_combo.addItem(pcs_name)
                        self.cluster_pcs_combo.setCurrentText(pcs_name)

                self.log(f"[INFO] Active cluster changed: {cluster_name}")
                return

    def move_bms_to_cluster(self) -> None:
        if not hasattr(self, "move_bms_name_edit"):
            return

        bms_name = self.move_bms_name_edit.text().strip()
        target_cluster_name = self.move_bms_target_cluster_combo.currentText().strip()

        if not bms_name:
            QMessageBox.warning(self, "Warning", "BMS name cannot be empty.")
            return

        if not target_cluster_name:
            QMessageBox.warning(self, "Warning", "Target cluster cannot be empty.")
            return

        target_cluster = None
        moving_device = None

        for cluster in self.site.clusters:
            for dev in list(cluster.bms_devices):
                if dev.name == bms_name:
                    moving_device = dev
                    cluster.bms_devices.remove(dev)
                    break

            if cluster.name == target_cluster_name:
                target_cluster = cluster

        if target_cluster is None:
            QMessageBox.warning(self, "Warning", f"Target cluster '{target_cluster_name}' not found.")
            return

        if moving_device is None:
            QMessageBox.warning(self, "Warning", f"BMS '{bms_name}' not found.")
            return

        target_cluster.bms_devices.append(moving_device)

        self.log(f"[INFO] Moved BMS {bms_name} to {target_cluster_name}")

        self.save_site_config()
        self.refresh_site_view()
        self.refresh_overview()


