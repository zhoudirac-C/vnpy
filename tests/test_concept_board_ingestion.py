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
    assert "concept.ingestion.enabled" in collect_tradingagents_config_keys()
    assert "concept.ingestion.catalog_path" in TRADINGAGENTS_CONFIG_KEYS
    assert "券商" in CONCEPT_CONFIG_HELP_TEXT["concept.ingestion.providers"]
    assert "AKShare" in CONCEPT_CONFIG_HELP_TEXT["concept.ingestion.providers"]


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
