from time import monotonic, sleep

from vnpy.event import EVENT_TIMER, Event


def test_scheduler_registers_timer_handler():
    """Scheduler should register timer events with EventEngine."""
    from vnpy_tradingagents.scheduler import TradingAgentsIntradayScheduler

    event_engine = FakeEventEngine()
    scheduler = TradingAgentsIntradayScheduler(event_engine, SlowJob(), interval_seconds=300)

    scheduler.start()

    assert event_engine.handlers[EVENT_TIMER] == scheduler.process_timer_event


def test_scheduler_throttles_timer_events_by_interval():
    """Scheduler should not run worker on every timer event."""
    from vnpy_tradingagents.scheduler import TradingAgentsIntradayScheduler

    clock = FakeClock([0, 60, 301])
    job = CountingJob()
    scheduler = TradingAgentsIntradayScheduler(
        FakeEventEngine(),
        job,
        interval_seconds=300,
        clock=clock,
    )

    scheduler.process_timer_event(Event(EVENT_TIMER))
    scheduler.process_timer_event(Event(EVENT_TIMER))
    scheduler.process_timer_event(Event(EVENT_TIMER))
    scheduler.shutdown()

    assert job.count == 2


def test_scheduler_does_not_block_event_thread():
    """Scheduler should submit worker jobs outside the EventEngine thread."""
    from vnpy_tradingagents.scheduler import TradingAgentsIntradayScheduler

    scheduler = TradingAgentsIntradayScheduler(
        FakeEventEngine(),
        SlowJob(),
        interval_seconds=300,
        clock=lambda: 0,
    )

    started = monotonic()
    scheduler.process_timer_event(Event(EVENT_TIMER))
    elapsed = monotonic() - started
    scheduler.shutdown()

    assert elapsed < 0.05


class FakeEventEngine:
    """Small EventEngine fake for scheduler tests."""

    def __init__(self) -> None:
        self.handlers = {}

    def register(self, event_type, handler) -> None:
        self.handlers[event_type] = handler

    def unregister(self, event_type, handler) -> None:
        if self.handlers.get(event_type) == handler:
            self.handlers.pop(event_type)


class CountingJob:
    """Count job invocations."""

    def __init__(self) -> None:
        self.count = 0

    def run(self) -> None:
        self.count += 1


class SlowJob:
    """Slow job fake."""

    def run(self) -> None:
        sleep(0.2)


class FakeClock:
    """Deterministic clock returning configured values."""

    def __init__(self, values: list[float]) -> None:
        self.values = values

    def __call__(self) -> float:
        return self.values.pop(0)
