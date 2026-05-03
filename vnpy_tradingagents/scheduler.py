from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from time import monotonic
from typing import Protocol

from vnpy.event import EVENT_TIMER, Event, EventEngine


class ScheduledJob(Protocol):
    """
    Scheduled TradingAgents job.
    """

    def run(self) -> None:
        pass


class TradingAgentsIntradayScheduler:
    """
    EventEngine timer scheduler for intraday TradingAgents jobs.
    """

    def __init__(
        self,
        event_engine: EventEngine,
        job: ScheduledJob,
        interval_seconds: int = 300,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        """"""
        self.event_engine: EventEngine = event_engine
        self.job: ScheduledJob = job
        self.interval_seconds: int = interval_seconds
        self.clock: Callable[[], float] = clock
        self.last_run_at: float | None = None
        self.executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=1)
        self.future: Future | None = None
        self.active: bool = False

    def start(self) -> None:
        """
        Register timer callback.
        """
        if self.active:
            return

        self.event_engine.register(EVENT_TIMER, self.process_timer_event)
        self.active = True

    def stop(self) -> None:
        """
        Unregister timer callback and stop worker executor.
        """
        if self.active:
            self.event_engine.unregister(EVENT_TIMER, self.process_timer_event)
            self.active = False
        self.shutdown()

    def shutdown(self) -> None:
        """
        Shutdown scheduler executor.
        """
        self.executor.shutdown(wait=True, cancel_futures=True)

    def process_timer_event(self, event: Event) -> None:
        """
        Throttled timer event callback.
        """
        if event.type != EVENT_TIMER:
            return

        now: float = self.clock()
        if self.last_run_at is not None and now - self.last_run_at < self.interval_seconds:
            return

        if self.future and not self.future.done():
            return

        self.last_run_at = now
        self.future = self.executor.submit(self.job.run)

    def trigger(self) -> None:
        """
        Optional manual trigger using the same throttle and async boundary.
        """
        self.process_timer_event(Event(EVENT_TIMER))
