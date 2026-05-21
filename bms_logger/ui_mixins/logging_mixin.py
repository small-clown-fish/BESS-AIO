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





class LoggingMixin:
    def log(self, message: str) -> None:
        if hasattr(self, "log_text"):
            self.log_text.append(message)

            # 限制最大行数（比如 1000 行）
            doc = self.log_text.document()
            max_lines = 1000
            if doc.blockCount() > max_lines:
                cursor = self.log_text.textCursor()
                cursor.movePosition(cursor.MoveOperation.Start)
                cursor.select(cursor.SelectionType.LineUnderCursor)
                cursor.removeSelectedText()
                cursor.deleteChar()

            # 自动滚动到底部
            self.log_text.verticalScrollBar().setValue(
                self.log_text.verticalScrollBar().maximum()
            )

        else:
            print(message)

        if message.startswith("[ERROR]") or message.startswith("[CUTOFF]"):
            self.operation_log(message)

    def control_log(self, message: str) -> None:
        if hasattr(self, "control_log_text"):
            self.control_log_text.append(message)

            doc = self.control_log_text.document()
            max_lines = 1000
            if doc.blockCount() > max_lines:
                cursor = self.control_log_text.textCursor()
                cursor.movePosition(cursor.MoveOperation.Start)
                cursor.select(cursor.SelectionType.LineUnderCursor)
                cursor.removeSelectedText()
                cursor.deleteChar()

            self.control_log_text.verticalScrollBar().setValue(
                self.control_log_text.verticalScrollBar().maximum()
            )

        else:
            print(message)

        self.operation_log(message)

    def operation_log(self, message: str) -> None:
        from datetime import datetime
        from pathlib import Path

        try:
            log_dir = self.get_profile_path("logs")
            log_dir.mkdir(parents=True, exist_ok=True)

            date_str = datetime.now().strftime("%Y%m%d")
            log_path = log_dir / f"operation_{date_str}.log"

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            line = f"{timestamp} {message}\n"

            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line)

        except Exception:
            pass

    def handle_load_operation_log(self) -> None:
        default_dir = self.get_profile_path("logs")

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load operation log",
            str(default_dir),
            "Log Files (*.log);;Text Files (*.txt);;All Files (*)",
        )

        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            self.log_text.setPlainText(content)
            self.log(f"[INFO] Loaded operation log: {path}")

        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to load operation log:\n{exc}")

    def handle_clear_log_view(self) -> None:
        if hasattr(self, "log_text"):
            self.log_text.clear()

