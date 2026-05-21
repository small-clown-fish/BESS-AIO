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





class StrategyMixin:
    def refresh_strategy_view(self) -> None:
        if not hasattr(self, "strategy_editor"):
            return

        try:
            self.strategy_engine.set_profile_dir(self.current_profile_dir)
            data = self.strategy_engine.load()
            self.strategy_editor.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))

            name = data.get("name", "-")
            version = data.get("version", "-")
            enabled = data.get("enabled", True)
            self.strategy_status_label.setText(
                f"Strategy: {name} | version={version} | enabled={enabled} | file={self.strategy_engine.strategy_path}"
            )

            if hasattr(self, "strategy_test_combo"):
                self.strategy_test_combo.blockSignals(True)
                self.strategy_test_combo.clear()
                for test in self.strategy_engine.fake_tests():
                    self.strategy_test_combo.addItem(str(test.get("name", "Unnamed")))
                self.strategy_test_combo.blockSignals(False)

        except Exception as exc:
            self.log(f"[ERROR] Failed to refresh strategy view: {exc}")

    def reload_strategy_config(self) -> None:
        try:
            self.strategy_engine.set_profile_dir(self.current_profile_dir)
            self.strategy_engine.load()
            self.refresh_strategy_view()
            self.log("[INFO] Strategy reloaded")
        except Exception as exc:
            QMessageBox.critical(self, "Strategy", f"Failed to reload strategy:\n{exc}")

    def save_strategy_from_editor(self) -> None:
        if not hasattr(self, "strategy_editor"):
            return

        try:
            data = json.loads(self.strategy_editor.toPlainText())
            errors = self.strategy_engine.validate(data)
            if errors:
                QMessageBox.warning(self, "Invalid Strategy", "\n".join(errors))
                return

            self.strategy_engine.save(data)
            self.refresh_strategy_view()
            self.log(f"[INFO] Strategy saved: {self.strategy_engine.strategy_path}")

        except Exception as exc:
            QMessageBox.critical(self, "Strategy", f"Failed to save strategy:\n{exc}")

    def import_strategy_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import strategy JSON",
            str(Path.cwd()),
            "JSON Files (*.json)",
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            errors = self.strategy_engine.validate(data)
            if errors:
                QMessageBox.warning(self, "Invalid Strategy", "\n".join(errors))
                return
            self.strategy_engine.save(data)
            self.refresh_strategy_view()
            self.log(f"[INFO] Strategy imported: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Strategy", f"Failed to import strategy:\n{exc}")

    def export_strategy_json(self) -> None:
        default_path = self.current_profile_dir / "strategy_export.json"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export strategy JSON",
            str(default_path),
            "JSON Files (*.json)",
        )
        if not path:
            return

        try:
            self.strategy_engine.save(json.loads(self.strategy_editor.toPlainText()))
            import shutil
            shutil.copy2(self.strategy_engine.strategy_path, Path(path))
            self.log(f"[INFO] Strategy exported: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Strategy", f"Failed to export strategy:\n{exc}")

    def reset_default_strategy(self) -> None:
        reply = QMessageBox.question(
            self,
            "Reset Strategy",
            "Reset current profile strategy.json to default?",
        )
        if reply != QMessageBox.Yes:
            return

        try:
            from .strategy_engine import DEFAULT_STRATEGY
            self.strategy_engine.save(DEFAULT_STRATEGY)
            self.refresh_strategy_view()
            self.log("[INFO] Strategy reset to default")
        except Exception as exc:
            QMessageBox.critical(self, "Strategy", f"Failed to reset strategy:\n{exc}")

    def _selected_strategy_fake_test(self) -> dict:
        if not hasattr(self, "strategy_test_combo"):
            return {}
        name = self.strategy_test_combo.currentText()
        for test in self.strategy_engine.fake_tests():
            if str(test.get("name", "")) == name:
                return test
        return {}

    def apply_selected_strategy_fake_test(self) -> None:
        test = self._selected_strategy_fake_test()
        if not test:
            QMessageBox.information(self, "Strategy Test", "No fake test selected.")
            return

        bms_scenario = str(test.get("bms_scenario", "normal"))
        pcs_scenario = str(test.get("pcs_scenario", "normal"))

        self.fake_mode = True
        if hasattr(self, "fake_mode_combo"):
            self.fake_mode_combo.setCurrentText("Fake")

        for dev in self.devices:
            dev["fake_scenario"] = bms_scenario

        for cfg in self.pcs_configs.values():
            cfg["fake_scenario"] = pcs_scenario

        try:
            self.save_devices_to_default()
            self.save_pcs_config()
            self.save_runtime_config()
        except Exception:
            pass

        if hasattr(self, "bms_fake_scenario_combo"):
            self.bms_fake_scenario_combo.setCurrentText(bms_scenario)
        if hasattr(self, "pcs_fake_scenario_combo"):
            self.pcs_fake_scenario_combo.setCurrentText(pcs_scenario)

        if hasattr(self, "strategy_test_result_text"):
            self.strategy_test_result_text.setPlainText(
                f"Applied fake test: {test.get('name')}\n"
                f"BMS scenario: {bms_scenario}\n"
                f"PCS scenario: {pcs_scenario}\n"
                "Mode switched to Fake. Use Start All to run the test."
            )

        self.log(
            f"[INFO] Strategy fake test applied: {test.get('name')} "
            f"(BMS={bms_scenario}, PCS={pcs_scenario})"
        )
        self.refresh_global_status_bar()

    def run_selected_strategy_fake_test(self) -> None:
        self.apply_selected_strategy_fake_test()
        self.start_all()

    def reset_fake_scenarios(self) -> None:
        for dev in self.devices:
            dev["fake_scenario"] = "normal"
        for cfg in self.pcs_configs.values():
            cfg["fake_scenario"] = "normal"

        try:
            self.save_devices_to_default()
            self.save_pcs_config()
        except Exception:
            pass

        if hasattr(self, "bms_fake_scenario_combo"):
            self.bms_fake_scenario_combo.setCurrentText("normal")
        if hasattr(self, "pcs_fake_scenario_combo"):
            self.pcs_fake_scenario_combo.setCurrentText("normal")
        if hasattr(self, "strategy_test_result_text"):
            self.strategy_test_result_text.setPlainText("Fake scenarios reset to normal.")

        self.log("[INFO] Fake scenarios reset to normal")

    # =========================
    # v3.0 Driver management
    # =========================
