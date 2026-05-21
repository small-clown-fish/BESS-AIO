from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QMessageBox

from ..hv_controller import HvWorkflowController, HvWorkflowWorker
from ..modbus_client import BmsModbusClient
from ..pcs_client import PcsClient
from ..client_factory import create_bms_client, create_pcs_client
from ..worker import HeartbeatWorker


class BmsControlMixin:
    def handle_start_heartbeat(self) -> None:
        device_name = self._get_selected_control_device()
        if not device_name:
            return

        if device_name in self.heartbeat_workers:
            self.control_log(f"[CONTROL] {device_name}: Heartbeat already running")
            self.heartbeat_state_label.setText("Running")
            return

        client = self._build_bms_client_for_device(device_name)
        if client is None:
            return

        # IMPORTANT: HeartbeatWorker runs in a Python background thread.
        # Never update Qt widgets directly from that thread; emit Qt signals
        # and let the main GUI thread handle UI updates. This fixes random
        # crashes when multiple BMS heartbeat workers are running.
        worker = HeartbeatWorker(
            device_name=device_name,
            client=client,
            callback=lambda name, value: self.bridge.heartbeat_written.emit(name, value),
            error_callback=lambda name, error: self.bridge.heartbeat_error.emit(name, error),
            interval=self.heartbeat_interval,
        )

        self.heartbeat_workers[device_name] = worker
        worker.start()

        self.heartbeat_state_label.setText("Starting")
        self.control_state_label.setText("Running")
        self.last_control_result_label.setText("Heartbeat started")
        self.control_log(f"[CONTROL] {device_name}: Heartbeat started")

    def handle_stop_heartbeat(self) -> None:
        device_name = self._get_selected_control_device()
        if not device_name:
            return

        worker = self.heartbeat_workers.get(device_name)
        if not worker:
            self.heartbeat_state_label.setText("Stopped")
            self.control_state_label.setText("Idle")
            self.last_control_result_label.setText("Heartbeat not running")
            self.control_log(f"[CONTROL] {device_name}: Heartbeat not running")
            self.last_heartbeat_status = "Stopped"
            self.refresh_global_status_bar()
            return

        worker.stop()
        worker.join(timeout=3.0)
        self.heartbeat_workers.pop(device_name, None)

        self.heartbeat_state_label.setText("Stopped")
        self.control_state_label.setText("Idle")
        self.last_control_result_label.setText("Heartbeat stopped")
        self.control_log(f"[CONTROL] {device_name}: Heartbeat stopped")
        self.last_heartbeat_status = "Stopped"
        self.refresh_global_status_bar()

    def _write_ems_cmd(self, device_name: str, cmd_value: int, cmd_name: str, confirm: bool) -> None:
        if confirm:
            reply = QMessageBox.question(
                self,
                f"Confirm {cmd_name}",
                f"Write EMS cmd {cmd_value} ({cmd_name}) to {device_name}?",
            )
            if reply != QMessageBox.Yes:
                return

        client = self._build_bms_client_for_device(device_name)
        if client is None:
            return

        self.control_state_label.setText("Executing")
        self.last_control_result_label.setText(f"EMS cmd {cmd_value}")
        self.last_ems_cmd_result_label.setText("Running")
        self.control_log(f"[CONTROL] {device_name}: EMS cmd {cmd_value} ({cmd_name}) started")

        try:
            if not client.connect():
                self.control_state_label.setText("Failed")
                self.last_ems_cmd_result_label.setText("Connect failed")
                self.control_log(f"[CONTROL] {device_name}: EMS cmd {cmd_value} failed - connect failed")
                QMessageBox.critical(self, "Error", f"Connect failed: {device_name}")
                return

            ok = client.write_ems_cmd(cmd_value)
            if ok:
                self.control_state_label.setText("Done")
                self.last_ems_cmd_result_label.setText(f"Success ({cmd_name})")
                self.control_log(f"[CONTROL] {device_name}: EMS cmd {cmd_value} ({cmd_name}) success")
            else:
                self.control_state_label.setText("Failed")
                self.last_ems_cmd_result_label.setText("Write failed")
                self.control_log(f"[CONTROL] {device_name}: EMS cmd {cmd_value} ({cmd_name}) failed - write failed")
                QMessageBox.critical(self, "Error", f"EMS cmd write failed: {device_name}")

        except Exception as exc:
            self.control_state_label.setText("Failed")
            self.last_ems_cmd_result_label.setText(str(exc))
            self.control_log(f"[CONTROL] {device_name}: EMS cmd {cmd_value} exception - {exc}")
            QMessageBox.critical(self, "Error", f"EMS cmd exception:\n{exc}")

        finally:
            try:
                client.close()
            except Exception:
                pass

    def handle_ems_cmd_stay(self) -> None:
        device_name = self._get_selected_control_device()
        if device_name:
            self._write_ems_cmd(device_name, 1, "Stay", confirm=False)

    def handle_ems_cmd_power_on(self) -> None:
        device_name = self._get_selected_control_device()
        if device_name:
            self._write_ems_cmd(device_name, 2, "Power On", confirm=True)

    def handle_ems_cmd_power_off(self) -> None:
        device_name = self._get_selected_control_device()
        if device_name:
            self._write_ems_cmd(device_name, 3, "Power Off", confirm=True)

    def handle_clear_fault(self) -> None:
        device_name = self._get_selected_control_device()
        if not device_name:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Clear Fault",
            f"Send clear fault command to {device_name}?",
        )
        if reply != QMessageBox.Yes:
            return

        client = self._build_bms_client_for_device(device_name)
        if client is None:
            return

        self.control_state_label.setText("Executing")
        self.last_control_result_label.setText("Running")
        self.control_log(f"[CONTROL] {device_name}: Clear Fault started")

        try:
            if not client.connect():
                self.control_state_label.setText("Failed")
                self.last_control_result_label.setText("Connect failed")
                self.control_log(f"[CONTROL] {device_name}: Clear Fault failed - connect failed")
                QMessageBox.critical(self, "Error", f"Connect failed: {device_name}")
                return

            ok = client.clear_fault()
            if ok:
                self.control_state_label.setText("Done")
                self.last_control_result_label.setText("Success")
                self.control_log(f"[CONTROL] {device_name}: Clear Fault success")
                QMessageBox.information(self, "Success", f"Clear Fault sent to {device_name}")
            else:
                self.control_state_label.setText("Failed")
                self.last_control_result_label.setText("Write failed")
                self.control_log(f"[CONTROL] {device_name}: Clear Fault failed - write failed")
                QMessageBox.critical(self, "Error", f"Clear Fault write failed: {device_name}")

        except Exception as exc:
            self.control_state_label.setText("Failed")
            self.last_control_result_label.setText(str(exc))
            self.control_log(f"[CONTROL] {device_name}: Clear Fault exception - {exc}")
            QMessageBox.critical(self, "Error", f"Clear Fault exception:\n{exc}")

        finally:
            try:
                client.close()
            except Exception:
                pass
