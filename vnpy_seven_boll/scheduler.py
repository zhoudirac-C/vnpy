"""
Lightweight in-process scheduler for seven-rail Bollinger scans.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import threading
from typing import Any

from vnpy.event import EVENT_TIMER, Event
from vnpy.trader.setting import SETTINGS

from .scanner import SevenBollScanService, build_scan_request_from_settings


class SevenBollScanScheduler:
    """
    Trigger seven-rail scans at configured wall-clock times.
    """

    def __init__(
        self,
        event_engine: Any,
        service: SevenBollScanService,
        settings: Mapping[str, Any] | None = None,
        now_factory: Any | None = None,
        async_scan: bool = True,
    ) -> None:
        self.event_engine = event_engine
        self.service = service
        self.settings = settings or SETTINGS
        self.now_factory = now_factory or datetime.now
        self.async_scan = async_scan
        self.enabled = _to_bool(self.settings.get("seven_boll.scan.enabled", True))
        self.schedule_times = _parse_schedule(self.settings.get("seven_boll.scan.schedule", "11:35,15:05"))
        self.active = False
        self.running = False
        self._lock = threading.Lock()
        self.last_trigger_key = ""
        self.last_error = ""
        self.last_started_at: datetime | None = None
        self.last_finished_at: datetime | None = None

    def start(self) -> None:
        if self.active:
            return
        self.active = True
        if self.event_engine is not None:
            self.event_engine.register(EVENT_TIMER, self.process_timer_event)

    def stop(self) -> None:
        self.active = False
        if self.event_engine is not None:
            self.event_engine.unregister(EVENT_TIMER, self.process_timer_event)

    def trigger(self, scan_type: str = "manual") -> bool:
        """
        Trigger one async scan.
        """
        with self._lock:
            if self.running:
                return False
            self.running = True

        if self.async_scan:
            thread = threading.Thread(target=self._run_once, args=(scan_type,), name="seven-boll-scan", daemon=True)
            thread.start()
        else:
            self._run_once(scan_type)
        return True

    def process_timer_event(self, event: Event) -> None:
        if not self.active or not self.enabled or event.type != EVENT_TIMER:
            return
        now = self.now_factory()
        current_time = now.strftime("%H:%M")
        if current_time not in self.schedule_times:
            return
        trigger_key = now.strftime("%Y%m%d") + current_time
        if trigger_key == self.last_trigger_key:
            return
        if self.trigger(_scan_type_for_time(current_time)):
            self.last_trigger_key = trigger_key

    def status(self) -> dict[str, Any]:
        summary = self.service.latest_summary
        return {
            "enabled": self.enabled,
            "active": self.active,
            "running": self.running,
            "schedule_times": list(self.schedule_times),
            "last_started_at": self.last_started_at,
            "last_finished_at": self.last_finished_at,
            "last_error": self.last_error,
            "latest_run_id": summary.run_id if summary else "",
            "latest_buy_count": len(summary.buy_candidates) if summary else 0,
            "latest_sell_count": len(summary.sell_candidates) if summary else 0,
        }

    def _run_once(self, scan_type: str) -> None:
        self.last_started_at = self.now_factory()
        self.last_error = ""
        try:
            self.service.scan(build_scan_request_from_settings(self.settings, scan_type=scan_type))
        except Exception as exc:
            self.last_error = str(exc)
        finally:
            self.last_finished_at = self.now_factory()
            with self._lock:
                self.running = False


def _parse_schedule(value: Any) -> tuple[str, ...]:
    text = str(value or "").strip()
    if not text:
        return ()
    for sep in (";", "，", "\n"):
        text = text.replace(sep, ",")
    return tuple(item.strip() for item in text.split(",") if item.strip())


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _scan_type_for_time(value: str) -> str:
    if value == "11:35":
        return "preview"
    if value == "15:05":
        return "official"
    return "scheduled"
