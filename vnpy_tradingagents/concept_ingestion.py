"""
Concept board ingestion service for TradingAgents context.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime
from typing import Any

from vnpy.event import EVENT_TIMER, Event, EventEngine
from vnpy.trader.setting import SETTINGS
from vnpy_router.concepts import ConceptBoard, ConceptBoardMember, ConceptBoardProvider, ConceptIngestionSummary
from vnpy_router.concept_storage import PeeweeConceptBoardRepository
from vnpy_router.providers.concepts import build_concept_providers


class ConceptBoardIngestionService:
    """
    Pull concept boards from providers in priority order and persist one snapshot.
    """

    def __init__(
        self,
        providers: Sequence[ConceptBoardProvider],
        repository: PeeweeConceptBoardRepository,
        max_boards_per_run: int = 0,
        max_concepts_per_symbol: int = 3,
    ) -> None:
        self.providers = list(providers)
        self.repository = repository
        self.max_boards_per_run = max(0, int(max_boards_per_run or 0))
        self.max_concepts_per_symbol = max(1, int(max_concepts_per_symbol or 3))
        self.latest_summary: ConceptIngestionSummary | None = None
        self._board_cursors: dict[tuple[str, str], int] = {}

    def run_once(self, board_type: str = "concept") -> ConceptIngestionSummary:
        """
        Run one ingestion attempt, using the first provider that returns data.
        """
        degraded_sources: list[str] = []
        errors: list[str] = []

        for provider in self.providers:
            provider_name = str(getattr(provider, "provider_name", provider.__class__.__name__))
            try:
                boards = list(provider.list_boards(board_type=board_type))
            except Exception as exc:
                errors.append(f"{provider_name}:{exc}")
                continue

            if not boards:
                degraded = str(getattr(provider, "degraded_reason", "") or "")
                if degraded:
                    degraded_sources.append(f"{provider_name}:{degraded}")
                else:
                    degraded_sources.append(f"{provider_name}:empty")
                continue

            selected_boards = self._select_board_batch(provider_name, board_type, boards)
            members: list[ConceptBoardMember] = []
            for board in selected_boards:
                try:
                    members.extend(provider.list_members(board))
                except Exception as exc:
                    errors.append(f"{provider_name}:{board.board_name}:{exc}")

            summary = self.repository.save_snapshot(
                boards=selected_boards,
                members=_dedup_members(members),
                max_concepts_per_symbol=self.max_concepts_per_symbol,
                provider_name=provider_name,
            )
            self.latest_summary = ConceptIngestionSummary(
                provider_name=summary.provider_name,
                board_count=summary.board_count,
                member_count=summary.member_count,
                link_count=summary.link_count,
                updated_symbols=summary.updated_symbols,
                degraded_sources=tuple(degraded_sources),
                errors=tuple(errors),
            )
            return self.latest_summary

        self.latest_summary = ConceptIngestionSummary(
            provider_name="",
            degraded_sources=tuple(degraded_sources),
            errors=tuple(errors),
        )
        return self.latest_summary

    def _select_board_batch(
        self,
        provider_name: str,
        board_type: str,
        boards: Sequence[ConceptBoard],
    ) -> list[ConceptBoard]:
        board_list = list(boards)
        if not board_list:
            return []
        if self.max_boards_per_run <= 0 or self.max_boards_per_run >= len(board_list):
            return board_list

        key = (provider_name, board_type)
        start = self._board_cursors.get(key, 0) % len(board_list)
        end = min(start + self.max_boards_per_run, len(board_list))
        selected = board_list[start:end]
        self._board_cursors[key] = 0 if end >= len(board_list) else end
        return selected


class ConceptBoardIngestionScheduler:
    """
    EventEngine-backed scheduler for low-frequency concept ingestion.
    """

    def __init__(
        self,
        event_engine: EventEngine,
        service: ConceptBoardIngestionService,
        enabled: bool = True,
        schedule_times: Sequence[str] = ("09:00",),
        board_type: str = "concept",
        datetime_clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.event_engine = event_engine
        self.service = service
        self.enabled = enabled
        self.schedule_times = frozenset(time.strip() for time in schedule_times if str(time).strip())
        self.board_type = board_type
        self.datetime_clock = datetime_clock
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.future: Future | None = None
        self.active = False
        self.last_run_key = ""
        self.last_started_at: datetime | None = None
        self.last_finished_at: datetime | None = None
        self.last_summary: ConceptIngestionSummary | None = None
        self.last_error = ""
        self.cancel_requested = False

    def start(self) -> None:
        if self.active:
            return
        self.event_engine.register(EVENT_TIMER, self.process_timer_event)
        self.active = True

    def stop(self) -> None:
        if self.active:
            self.event_engine.unregister(EVENT_TIMER, self.process_timer_event)
            self.active = False
        self.shutdown()

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=True)

    def process_timer_event(self, event: Event) -> None:
        if event.type != EVENT_TIMER or not self.enabled:
            return
        now = self.datetime_clock()
        minute = now.strftime("%H:%M")
        if minute not in self.schedule_times:
            return
        run_key = now.strftime("%Y-%m-%d %H:%M")
        if run_key == self.last_run_key:
            return
        if self.trigger():
            self.last_run_key = run_key

    def trigger(self) -> bool:
        """
        Manually trigger concept ingestion.
        """
        if self.future and not self.future.done():
            self.last_error = "concept_ingestion_busy"
            return False
        self.last_started_at = self.datetime_clock()
        self.last_finished_at = None
        self.last_summary = None
        self.last_error = ""
        self.cancel_requested = False
        self.future = self.executor.submit(self._run_job)
        return True

    def cancel(self) -> bool:
        if not self.future or self.future.done():
            return False
        self.cancel_requested = True
        self.future.cancel()
        return True

    def status(self) -> dict[str, Any]:
        if self.future and not self.future.done():
            state = "cancel_requested" if self.cancel_requested else "running"
        elif self.last_started_at:
            state = "completed" if not self.last_error else "failed"
        else:
            state = "idle"
        return {
            "state": state,
            "active": self.active,
            "enabled": self.enabled,
            "schedule_times": sorted(self.schedule_times),
            "board_type": self.board_type,
            "last_started_at": self.last_started_at,
            "last_finished_at": self.last_finished_at,
            "last_summary": _summary_to_dict(self.last_summary),
            "last_error": self.last_error,
            "cancel_requested": self.cancel_requested,
        }

    def apply_settings(
        self,
        *,
        enabled: bool | None = None,
        schedule_times: Sequence[str] | None = None,
    ) -> None:
        if enabled is not None:
            self.enabled = enabled
        if schedule_times is not None:
            self.schedule_times = frozenset(time.strip() for time in schedule_times if str(time).strip())

    def _run_job(self) -> ConceptIngestionSummary:
        try:
            if self.cancel_requested:
                summary = ConceptIngestionSummary(provider_name="", errors=("cancel_requested",))
            else:
                summary = self.service.run_once(board_type=self.board_type)
            self.last_summary = summary
            return summary
        except Exception as exc:
            self.last_error = str(exc)
            raise
        finally:
            self.last_finished_at = self.datetime_clock()


def build_concept_ingestion_service(
    repository: PeeweeConceptBoardRepository,
    settings: Mapping[str, Any] | None = None,
) -> ConceptBoardIngestionService:
    """
    Build the default broker-first concept ingestion service.
    """
    source = settings or SETTINGS
    providers = build_concept_providers(
        _split_names(source.get("concept.ingestion.providers", "broker,local_catalog,akshare")),
        catalog_path=source.get("concept.ingestion.catalog_path", "")
        or source.get("news.entity.catalog_path", "")
        or source.get("financial.ingestion.catalog_path", ""),
        akshare_max_retries=_to_int(source.get("concept.ingestion.akshare.max_retries", 3), 3),
        akshare_retry_backoff_seconds=_to_float(
            source.get("concept.ingestion.akshare.retry_backoff_seconds", 2.0),
            2.0,
        ),
    )
    return ConceptBoardIngestionService(
        providers=providers,
        repository=repository,
        max_boards_per_run=_to_int(source.get("concept.ingestion.max_boards_per_run", 0), 0),
        max_concepts_per_symbol=_to_int(source.get("concept.ingestion.max_concepts_per_symbol", 3), 3),
    )


def concept_schedule_times(settings: Mapping[str, Any]) -> tuple[str, ...]:
    """
    Parse daily concept ingestion schedule from settings.
    """
    return tuple(_split_names(settings.get("concept.ingestion.schedule", "09:00"))) or ("09:00",)


def _dedup_members(members: Sequence[ConceptBoardMember]) -> list[ConceptBoardMember]:
    result: list[ConceptBoardMember] = []
    seen: set[tuple[str, str, str]] = set()
    for member in members:
        key = (member.board_id, member.vt_symbol, member.provider_name)
        if key in seen:
            continue
        seen.add(key)
        result.append(member)
    return result


def _split_names(value: Any) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    for sep in ("，", ";", "\n"):
        text = text.replace(sep, ",")
    return [item.strip() for item in text.split(",") if item.strip()]


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _summary_to_dict(summary: ConceptIngestionSummary | None) -> dict[str, Any] | None:
    if summary is None:
        return None
    return asdict(summary)
