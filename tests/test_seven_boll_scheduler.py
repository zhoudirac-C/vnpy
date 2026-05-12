from __future__ import annotations

from datetime import datetime

from vnpy.event import EVENT_TIMER, Event
from vnpy.trader.constant import Interval


def test_seven_boll_scheduler_registers_timer_handler() -> None:
    from vnpy_seven_boll.scheduler import SevenBollScanScheduler

    event_engine = FakeEventEngine()
    scheduler = SevenBollScanScheduler(event_engine, RecordingScanService(), settings={})

    scheduler.start()

    assert event_engine.handlers[EVENT_TIMER] == scheduler.process_timer_event


def test_seven_boll_scheduler_triggers_preview_once_per_minute() -> None:
    from vnpy_seven_boll.scheduler import SevenBollScanScheduler

    service = RecordingScanService()
    scheduler = SevenBollScanScheduler(
        FakeEventEngine(),
        service,
        settings={"seven_boll.scan.enabled": True, "seven_boll.scan.schedule": "11:35,15:05"},
        now_factory=lambda: datetime(2024, 1, 2, 11, 35),
        async_scan=False,
    )
    scheduler.start()

    scheduler.process_timer_event(Event(EVENT_TIMER))
    scheduler.process_timer_event(Event(EVENT_TIMER))

    assert len(service.requests) == 1
    assert service.requests[0].interval == Interval.DAILY
    assert service.requests[0].scan_type == "preview"


def test_seven_boll_scheduler_marks_after_close_as_official() -> None:
    from vnpy_seven_boll.scheduler import SevenBollScanScheduler

    service = RecordingScanService()
    scheduler = SevenBollScanScheduler(
        FakeEventEngine(),
        service,
        settings={"seven_boll.scan.enabled": True, "seven_boll.scan.schedule": "15:05"},
        now_factory=lambda: datetime(2024, 1, 2, 15, 5),
        async_scan=False,
    )
    scheduler.start()

    scheduler.process_timer_event(Event(EVENT_TIMER))

    assert service.requests[0].scan_type == "official"
    assert service.requests[0].interval == Interval.DAILY


def test_seven_boll_scheduler_rejects_concurrent_scan() -> None:
    from vnpy_seven_boll.scheduler import SevenBollScanScheduler

    service = RecordingScanService()
    scheduler = SevenBollScanScheduler(FakeEventEngine(), service, settings={}, async_scan=False)
    scheduler.running = True

    accepted = scheduler.trigger()

    assert accepted is False
    assert service.requests == []


def test_seven_boll_scheduler_records_failure_without_raising() -> None:
    from vnpy_seven_boll.scheduler import SevenBollScanScheduler

    scheduler = SevenBollScanScheduler(FakeEventEngine(), FailingScanService(), settings={}, async_scan=False)

    accepted = scheduler.trigger(scan_type="official")

    assert accepted is True
    status = scheduler.status()
    assert status["running"] is False
    assert "scan failed" in status["last_error"]


class FakeEventEngine:
    def __init__(self) -> None:
        self.handlers = {}

    def register(self, event_type, handler) -> None:
        self.handlers[event_type] = handler

    def unregister(self, event_type, handler) -> None:
        if self.handlers.get(event_type) == handler:
            self.handlers.pop(event_type)


class RecordingScanService:
    def __init__(self) -> None:
        self.requests = []
        self.latest_summary = None

    def scan(self, request):
        self.requests.append(request)
        return None


class FailingScanService:
    latest_summary = None

    def scan(self, request):
        raise RuntimeError("scan failed")
