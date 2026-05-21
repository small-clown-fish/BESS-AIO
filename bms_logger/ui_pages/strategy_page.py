from __future__ import annotations

from pathlib import Path
import csv
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QMessageBox,
    QSizePolicy,
)

def _build_strategy_tab(self, tabs: QTabWidget) -> None:
        strategy_tab = QWidget()
        layout = QVBoxLayout(strategy_tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        top_group = QGroupBox("Strategy Engine")
        top_layout = QVBoxLayout(top_group)
        self.strategy_status_label = QLabel("Strategy: -")
        self.strategy_status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        top_layout.addWidget(self.strategy_status_label)

        btn_row = QHBoxLayout()
        self.load_strategy_btn = QPushButton("Reload Strategy")
        self.load_strategy_btn.clicked.connect(self.reload_strategy_config)
        self.save_strategy_btn = QPushButton("Save Strategy")
        self.save_strategy_btn.clicked.connect(self.save_strategy_from_editor)
        self.import_strategy_btn = QPushButton("Import Strategy JSON")
        self.import_strategy_btn.clicked.connect(self.import_strategy_json)
        self.export_strategy_btn = QPushButton("Export Strategy JSON")
        self.export_strategy_btn.clicked.connect(self.export_strategy_json)
        self.reset_strategy_btn = QPushButton("Reset Default")
        self.reset_strategy_btn.clicked.connect(self.reset_default_strategy)

        for btn in [
            self.load_strategy_btn,
            self.save_strategy_btn,
            self.import_strategy_btn,
            self.export_strategy_btn,
            self.reset_strategy_btn,
        ]:
            btn_row.addWidget(btn)
        btn_row.addStretch()
        top_layout.addLayout(btn_row)
        layout.addWidget(top_group)

        editor_group = QGroupBox("Active Strategy JSON")
        editor_layout = QVBoxLayout(editor_group)
        self.strategy_editor = QTextEdit()
        self.strategy_editor.setMinimumHeight(260)
        self.strategy_editor.setPlaceholderText("strategy.json")
        editor_layout.addWidget(self.strategy_editor)
        layout.addWidget(editor_group, 1)

        test_group = QGroupBox("Fake Scenario Test")
        test_layout = QGridLayout(test_group)
        self.strategy_test_combo = QComboBox()
        self.apply_strategy_test_btn = QPushButton("Apply Fake Scenario")
        self.apply_strategy_test_btn.clicked.connect(self.apply_selected_strategy_fake_test)
        self.run_strategy_fake_btn = QPushButton("Apply + Start All")
        self.run_strategy_fake_btn.clicked.connect(self.run_selected_strategy_fake_test)
        self.clear_strategy_fake_btn = QPushButton("Reset Fake Scenarios")
        self.clear_strategy_fake_btn.clicked.connect(self.reset_fake_scenarios)
        self.strategy_test_result_text = QTextEdit()
        self.strategy_test_result_text.setReadOnly(True)
        self.strategy_test_result_text.setMinimumHeight(120)

        test_layout.addWidget(QLabel("Test Scenario"), 0, 0)
        test_layout.addWidget(self.strategy_test_combo, 0, 1)
        test_layout.addWidget(self.apply_strategy_test_btn, 0, 2)
        test_layout.addWidget(self.run_strategy_fake_btn, 0, 3)
        test_layout.addWidget(self.clear_strategy_fake_btn, 0, 4)
        test_layout.addWidget(self.strategy_test_result_text, 1, 0, 1, 5)
        layout.addWidget(test_group)

        tabs.addTab(strategy_tab, "Strategy")

