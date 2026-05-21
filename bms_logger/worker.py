from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional

from .data_model import normalize_telemetry_snapshot


class DeviceWorker(threading.Thread):
    """
    单设备独立采集线程。

    v3.0 phase 5 additions:
    - initial_delay 支持错峰启动，避免所有设备同时连接/读取。
    - status_callback 输出任务状态，用于 Scheduler/Tasks 面板。
    """

    def __init__(
        self,
        device_name: str,
        client: Any,
        interval: float,
        callback: Callable[[str, Dict[str, Any]], None],
        error_callback: Optional[Callable[[str, str], None]] = None,
        status_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        initial_delay: float = 0.0,
    ) -> None:
        super().__init__(daemon=True)
        self.device_name = device_name
        self.client = client
        self.interval = interval
        self.callback = callback
        self.error_callback = error_callback
        self.status_callback = status_callback
        self.initial_delay = max(0.0, float(initial_delay))
        self.running = False

    def _status(
        self,
        status: str,
        message: str = "-",
        latency_ms: float = 0.0,
        read_ok: bool = False,
        error: bool = False,
    ) -> None:
        if not self.status_callback:
            return
        try:
            self.status_callback(
                self.device_name,
                {
                    "status": status,
                    "last_message": message,
                    "last_latency_ms": latency_ms,
                    "read_ok": read_ok,
                    "error": error,
                },
            )
        except Exception:
            pass

    def stop(self) -> None:
        self.running = False

    def run(self) -> None:
        self.running = True

        if self.initial_delay > 0:
            self._status("Scheduled", f"Initial delay {self.initial_delay:.1f}s")
            time.sleep(self.initial_delay)

        try:
            if not self.client.connect():
                self._status("Error", "Connect failed", error=True)
                if self.error_callback:
                    self.error_callback(self.device_name, "Connect failed")
                return
        except Exception as exc:
            self._status("Error", f"Connect exception: {exc}", error=True)
            if self.error_callback:
                self.error_callback(self.device_name, f"Connect exception: {exc}")
            return

        self._status("Running", "Connected")

        while self.running:
            start = time.time()

            try:
                raw_snapshot = self.client.read_telemetry_snapshot()
                if raw_snapshot is None:
                    self._status("Timeout", "Read telemetry failed", error=True)
                    if self.error_callback:
                        self.error_callback(self.device_name, "Read telemetry failed")
                else:
                    point_catalog = {}
                    try:
                        getter = getattr(self.client, "get_point_catalog", None)
                        if callable(getter):
                            point_catalog = getter()
                    except Exception:
                        point_catalog = {}

                    driver_key = getattr(self.client, "driver_key", self.client.__class__.__name__)
                    snapshot = normalize_telemetry_snapshot(
                        raw_snapshot,
                        device_name=self.device_name,
                        driver_key=str(driver_key),
                        device_type="BMS",
                        point_catalog=point_catalog,
                    )
                    if snapshot is None:
                        self._status("Error", "Normalize telemetry failed", error=True)
                        if self.error_callback:
                            self.error_callback(self.device_name, "Normalize telemetry failed")
                    else:
                        latency_ms = (time.time() - start) * 1000.0
                        self._status("Running", "Read OK", latency_ms=latency_ms, read_ok=True)
                        self.callback(self.device_name, snapshot)

            except Exception as exc:
                self._status("Error", f"Read exception: {exc}", error=True)
                if self.error_callback:
                    self.error_callback(self.device_name, f"Read exception: {exc}")

            elapsed = time.time() - start
            sleep_time = max(0.0, self.interval - elapsed)
            time.sleep(sleep_time)

        self._status("Stopped", "Worker stopped")
        try:
            self.client.close()
        except Exception:
            pass


class HeartbeatWorker(threading.Thread):
    """
    每台设备一个心跳线程：
    - 每秒写一次
    - 数值从 0 到 255
    - 到 255 后回到 0
    """

    def __init__(
        self,
        device_name: str,
        client: Any,
        callback: Optional[Callable[[str, int], None]] = None,
        error_callback: Optional[Callable[[str, str], None]] = None,
        interval: float = 1.0,
    ) -> None:
        super().__init__(daemon=True)
        self.device_name = device_name
        self.client = client
        self.callback = callback
        self.error_callback = error_callback
        self.interval = interval
        self.running = False
        self.value = 0

    def stop(self) -> None:
        self.running = False

    def run(self) -> None:
        self.running = True

        try:
            if not self.client.connect():
                if self.error_callback:
                    try:
                        self.error_callback(self.device_name, "Heartbeat connect failed")
                    except Exception:
                        pass
                return
        except Exception as exc:
            if self.error_callback:
                try:
                    self.error_callback(self.device_name, f"Heartbeat connect exception: {exc}")
                except Exception:
                    pass
            return

        while self.running:
            start = time.time()

            try:
                ok = self.client.write_heartbeat(self.value)
                if ok:
                    if self.callback:
                        try:
                            self.callback(self.device_name, self.value)
                        except Exception:
                            pass
                    self.value = (self.value + 1) % 256
                else:
                    if self.error_callback:
                        try:
                            self.error_callback(self.device_name, "Heartbeat write failed")
                        except Exception:
                            pass
            except Exception as exc:
                if self.error_callback:
                    try:
                        self.error_callback(self.device_name, f"Heartbeat exception: {exc}")
                    except Exception:
                        pass

            elapsed = time.time() - start
            sleep_time = max(0.0, self.interval - elapsed)
            time.sleep(sleep_time)

        try:
            self.client.close()
        except Exception:
            pass


class PcsPollingWorker(threading.Thread):
    """Poll one PCS device periodically and return a normalized lightweight snapshot.

    This mirrors DeviceWorker for BMS, but is profile-driven and reads a selected
    list of PCS points. It is intentionally tolerant: a single bad point is
    returned as an error in point_errors instead of killing the whole cycle.
    """

    def __init__(
        self,
        pcs_name: str,
        client: Any,
        interval: float,
        point_names: list[str],
        callback: Callable[[str, Dict[str, Any]], None],
        error_callback: Optional[Callable[[str, str], None]] = None,
        status_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        initial_delay: float = 0.0,
    ) -> None:
        super().__init__(daemon=True)
        self.pcs_name = pcs_name
        self.client = client
        self.interval = max(0.2, float(interval))
        self.point_names = list(point_names)
        self.callback = callback
        self.error_callback = error_callback
        self.status_callback = status_callback
        self.initial_delay = max(0.0, float(initial_delay))
        self.running = False

    def stop(self) -> None:
        self.running = False

    def _status(self, status: str, message: str = "-", latency_ms: float = 0.0, read_ok: bool = False, error: bool = False) -> None:
        if not self.status_callback:
            return
        try:
            self.status_callback(
                self.pcs_name,
                {
                    "status": status,
                    "last_message": message,
                    "last_latency_ms": latency_ms,
                    "read_ok": read_ok,
                    "error": error,
                    "device_type": "PCS",
                },
            )
        except Exception:
            pass

    def run(self) -> None:
        self.running = True
        if self.initial_delay > 0:
            self._status("Scheduled", f"Initial delay {self.initial_delay:.1f}s")
            time.sleep(self.initial_delay)

        try:
            if not self.client.connect():
                self._status("Error", "PCS connect failed", error=True)
                if self.error_callback:
                    self.error_callback(self.pcs_name, "PCS connect failed")
                return
        except Exception as exc:
            self._status("Error", f"PCS connect exception: {exc}", error=True)
            if self.error_callback:
                self.error_callback(self.pcs_name, f"PCS connect exception: {exc}")
            return

        self._status("Running", "PCS connected")

        while self.running:
            start = time.time()
            snapshot: Dict[str, Any] = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "device_type": "PCS",
                "driver_key": getattr(self.client, "config", {}).get("driver", "generic_modbus_pcs") if hasattr(self.client, "config") else "generic_modbus_pcs",
                "points": {},
                "raw": {},
                "point_errors": {},
            }
            try:
                for point_name in self.point_names:
                    try:
                        raw = self.client.read_raw(point_name)
                        try:
                            value = self.client.read_value(point_name)
                        except Exception:
                            value = raw
                        snapshot["raw"][point_name] = raw
                        snapshot["points"][point_name] = value
                        # Promote common points for CSV/quick display convenience.
                        snapshot[point_name] = value
                    except Exception as exc:
                        snapshot["point_errors"][point_name] = str(exc)

                latency_ms = (time.time() - start) * 1000.0
                self._status("Running", "PCS read OK", latency_ms=latency_ms, read_ok=True)
                self.callback(self.pcs_name, snapshot)
            except Exception as exc:
                self._status("Error", f"PCS read exception: {exc}", error=True)
                if self.error_callback:
                    self.error_callback(self.pcs_name, f"PCS read exception: {exc}")

            elapsed = time.time() - start
            time.sleep(max(0.0, self.interval - elapsed))

        self._status("Stopped", "PCS worker stopped")
        try:
            self.client.close()
        except Exception:
            pass
