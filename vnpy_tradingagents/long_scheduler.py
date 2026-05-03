from dataclasses import dataclass
from typing import Protocol

from .batch import BatchRunSummary


@dataclass(frozen=True)
class LongHorizonSchedule:
    """
    Named long-horizon run slots.
    """

    slot_names: tuple[str, ...]

    @classmethod
    def default(cls) -> "LongHorizonSchedule":
        """
        Return the standard A-share long-horizon slots.
        """
        return cls(slot_names=("pre_open", "after_close", "weekend"))


@dataclass(frozen=True)
class LongRunResult:
    """
    Scheduler result for one slot.
    """

    slot_name: str
    trade_date: str
    skipped: bool
    summary: BatchRunSummary


class BatchJob(Protocol):
    """
    Batch job protocol used by the scheduler.
    """

    def run(
        self,
        symbols: list[str],
        trade_date: str,
        batch_run_id: str | None = None,
    ) -> BatchRunSummary:
        pass


class InMemoryLongRunRegistry:
    """
    In-memory idempotency registry for long-horizon scheduling.
    """

    def __init__(self) -> None:
        """"""
        self._results: dict[tuple[str, str], LongRunResult] = {}
        self.active_intent_keys: set[tuple[str, str]] = set()

    def get(self, slot_name: str, trade_date: str) -> LongRunResult | None:
        """
        Return a prior result for the slot/date pair.
        """
        return self._results.get((slot_name, trade_date))

    def mark(self, result: LongRunResult) -> None:
        """
        Persist the latest slot/date result and active intent keys.
        """
        self._results[(result.slot_name, result.trade_date)] = result
        for intent in result.summary.intents:
            self.active_intent_keys.add((intent.vt_symbol, intent.trade_date))


class LongHorizonScheduler:
    """
    Idempotent scheduler for pre-open, after-close and weekend batch jobs.
    """

    def __init__(
        self,
        job: BatchJob,
        registry: InMemoryLongRunRegistry,
        schedule: LongHorizonSchedule | None = None,
    ) -> None:
        """"""
        self.job: BatchJob = job
        self.registry: InMemoryLongRunRegistry = registry
        self.schedule: LongHorizonSchedule = schedule or LongHorizonSchedule.default()

    def run_slot(
        self,
        slot_name: str,
        symbols: list[str],
        trade_date: str,
        force: bool = False,
    ) -> LongRunResult:
        """
        Run a named slot once per trade date unless force is requested.
        """
        if slot_name not in self.schedule.slot_names:
            raise ValueError(f"unknown long-horizon slot: {slot_name}")

        existing = self.registry.get(slot_name, trade_date)
        if existing is not None and not force:
            return LongRunResult(
                slot_name=slot_name,
                trade_date=trade_date,
                skipped=True,
                summary=existing.summary,
            )

        batch_run_id: str = f"{slot_name}:{trade_date}"
        summary: BatchRunSummary = self.job.run(symbols, trade_date, batch_run_id=batch_run_id)
        result = LongRunResult(
            slot_name=slot_name,
            trade_date=trade_date,
            skipped=False,
            summary=summary,
        )
        self.registry.mark(result)
        return result
