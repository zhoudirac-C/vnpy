from peewee import SqliteDatabase


def test_concept_ingestion_service_uses_priority_chain_and_persists_links() -> None:
    from vnpy_router.concept_storage import PeeweeConceptBoardRepository
    from vnpy_router.concepts import ConceptBoard, ConceptBoardMember
    from vnpy_tradingagents.concept_ingestion import ConceptBoardIngestionService

    database = SqliteDatabase(":memory:")
    repository = PeeweeConceptBoardRepository(database)
    repository.create_schema()

    broker = EmptyProvider("broker_xt", degraded_reason="broker_xt_unavailable")
    catalog = StaticProvider(
        provider_name="local_security_catalog",
        boards=[
            ConceptBoard(
                board_type="concept",
                board_code="机器人概念",
                board_name="机器人概念",
                provider_name="local_security_catalog",
            )
        ],
        members={
            "local_security_catalog:concept:机器人概念": [
                ConceptBoardMember(
                    board_id="local_security_catalog:concept:机器人概念",
                    vt_symbol="603112.SSE",
                    name="华翔股份",
                    provider_name="local_security_catalog",
                )
            ]
        },
    )

    service = ConceptBoardIngestionService(
        providers=[broker, catalog],
        repository=repository,
        max_concepts_per_symbol=3,
    )

    summary = service.run_once(board_type="concept")

    assert summary.provider_name == "local_security_catalog"
    assert summary.board_count == 1
    assert summary.member_count == 1
    assert summary.updated_symbols == ("603112.SSE",)
    assert summary.degraded_sources == ("broker_xt:broker_xt_unavailable",)
    assert repository.list_security_concepts("603112.SSE") == ["机器人概念"]


def test_concept_ingestion_settings_are_owned_by_tradingagents_config_tab() -> None:
    from vnpy.trader.setting import SETTINGS
    from vnpy_tradingagents.ui.widget import (
        CONCEPT_CONFIG_HELP_TEXT,
        TRADINGAGENTS_CONFIG_KEYS,
        collect_tradingagents_config_keys,
    )

    assert SETTINGS["concept.ingestion.providers"] == "broker,local_catalog,akshare"
    assert SETTINGS["concept.ingestion.max_boards_per_run"] == 20
    assert SETTINGS["concept.ingestion.akshare.max_retries"] == 3
    assert SETTINGS["concept.ingestion.akshare.retry_backoff_seconds"] == 2.0
    assert "concept.ingestion.enabled" in collect_tradingagents_config_keys()
    assert "concept.ingestion.catalog_path" in TRADINGAGENTS_CONFIG_KEYS
    assert "券商" in CONCEPT_CONFIG_HELP_TEXT["concept.ingestion.providers"]
    assert "AKShare" in CONCEPT_CONFIG_HELP_TEXT["concept.ingestion.providers"]
    assert "重试" in CONCEPT_CONFIG_HELP_TEXT["concept.ingestion.akshare.max_retries"]


def test_concept_ingestion_service_batches_boards_with_cursor() -> None:
    from vnpy_router.concepts import ConceptBoard, ConceptBoardMember
    from vnpy_tradingagents.concept_ingestion import ConceptBoardIngestionService

    boards = [
        ConceptBoard(
            board_type="concept",
            board_code=f"BK{index}",
            board_name=f"概念{index}",
            provider_name="akshare",
        )
        for index in range(1, 6)
    ]
    provider = StaticProvider(
        provider_name="akshare",
        boards=boards,
        members={
            board.board_id: [
                ConceptBoardMember(
                    board_id=board.board_id,
                    vt_symbol="603112.SSE",
                    name="华翔股份",
                    provider_name="akshare",
                )
            ]
            for board in boards
        },
    )
    repository = RecordingConceptRepository()
    service = ConceptBoardIngestionService(
        providers=[provider],
        repository=repository,
        max_boards_per_run=2,
    )

    first = service.run_once()
    second = service.run_once()
    third = service.run_once()
    fourth = service.run_once()

    assert [board.board_name for board in repository.saved_batches[0]] == ["概念1", "概念2"]
    assert [board.board_name for board in repository.saved_batches[1]] == ["概念3", "概念4"]
    assert [board.board_name for board in repository.saved_batches[2]] == ["概念5"]
    assert [board.board_name for board in repository.saved_batches[3]] == ["概念1", "概念2"]
    assert first.board_count == 2
    assert second.board_count == 2
    assert third.board_count == 1
    assert fourth.board_count == 2


def test_tradingagents_engine_delegates_concept_ingestion_scheduler() -> None:
    from vnpy.event import EventEngine
    from vnpy_tradingagents.engine import TradingAgentsEngine

    engine = TradingAgentsEngine(None, EventEngine())  # type: ignore[arg-type]
    scheduler = FakeConceptScheduler()

    engine.set_concept_ingestion_scheduler(scheduler)

    assert engine.trigger_concept_ingestion() == "concept_ingestion_triggered"
    assert engine.get_concept_ingestion_status()["state"] == "running"
    assert engine.cancel_concept_ingestion() is True
    assert scheduler.triggered == 1
    assert scheduler.cancelled == 1


def test_tradingagents_ui_declares_concept_ingestion_manual_controls() -> None:
    from pathlib import Path
    from vnpy_tradingagents.ui.widget import build_concept_ingestion_status_text

    source = Path("vnpy_tradingagents/ui/widget.py").read_text(encoding="utf-8")

    assert "self.concept_ingestion_trigger_button = QtWidgets.QPushButton(\"拉取概念入库\")" in source
    assert "self.concept_ingestion_trigger_button.clicked.connect(self.trigger_concept_ingestion)" in source
    assert "self.concept_ingestion_timer.timeout.connect(self.refresh_concept_ingestion_status)" in source
    assert "self._set_concept_ingestion_running(True)" in source

    text = build_concept_ingestion_status_text(
        {
            "state": "running",
            "active": True,
            "enabled": True,
            "schedule_times": ["09:00"],
            "last_summary": {
                "provider_name": "akshare",
                "board_count": 5,
                "member_count": 300,
                "link_count": 300,
                "updated_symbols": ["603112.SSE"],
                "degraded_sources": ["broker_xt:broker_xt_unavailable"],
                "errors": [],
            },
        }
    )
    assert "concept_ingestion_status=running" in text
    assert "provider=akshare" in text
    assert "board_count=5" in text
    assert "broker_xt:broker_xt_unavailable" in text


class EmptyProvider:
    def __init__(self, provider_name: str, degraded_reason: str = "") -> None:
        self.provider_name = provider_name
        self.degraded_reason = degraded_reason

    def list_boards(self, board_type: str = "concept"):
        return []

    def list_members(self, board):
        return []


class StaticProvider:
    def __init__(self, provider_name: str, boards, members) -> None:
        self.provider_name = provider_name
        self.boards = boards
        self.members = members
        self.degraded_reason = ""

    def list_boards(self, board_type: str = "concept"):
        return [board for board in self.boards if board.board_type == board_type]

    def list_members(self, board):
        return self.members.get(board.board_id, [])


class FakeConceptScheduler:
    def __init__(self) -> None:
        self.triggered = 0
        self.cancelled = 0

    def trigger(self):
        self.triggered += 1
        return True

    def status(self):
        return {"state": "running"}

    def cancel(self):
        self.cancelled += 1
        return True


class RecordingConceptRepository:
    def __init__(self) -> None:
        self.saved_batches = []

    def save_snapshot(self, boards, members, max_concepts_per_symbol=3, provider_name=""):
        from vnpy_router.concepts import ConceptIngestionSummary

        self.saved_batches.append(list(boards))
        return ConceptIngestionSummary(
            provider_name=provider_name,
            board_count=len(boards),
            member_count=len(members),
            link_count=len(members),
            updated_symbols=tuple(sorted({member.vt_symbol for member in members})),
        )
