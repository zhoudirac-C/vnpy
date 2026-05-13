from pathlib import Path


def test_local_concept_catalog_provider_builds_boards_and_members(tmp_path: Path) -> None:
    from vnpy_router.providers.concepts import LocalConceptCatalogProvider

    catalog_path = tmp_path / "catalog.csv"
    catalog_path.write_text(
        "\n".join(
            [
                "vt_symbol,symbol,exchange,name,industry,sector,concept_tags",
                "603112.SSE,603112,SSE,华翔股份,汽车零部件,制造业,机器人概念|光伏概念",
                "002048.SZSE,002048,SZSE,宁波华翔,汽车零部件,制造业,机器人概念",
            ]
        ),
        encoding="utf-8",
    )

    provider = LocalConceptCatalogProvider(catalog_path)
    concept_boards = provider.list_boards("concept")
    concept_names = [board.board_name for board in concept_boards]

    assert concept_names == ["机器人概念", "光伏概念"]
    robot_members = provider.list_members(concept_boards[0])
    assert [member.vt_symbol for member in robot_members] == ["002048.SZSE", "603112.SSE"]
    assert [member.name for member in robot_members] == ["宁波华翔", "华翔股份"]

    industry_boards = provider.list_boards("industry")
    assert [board.board_name for board in industry_boards] == ["汽车零部件"]


def test_broker_concept_provider_uses_injected_xtdata_without_hard_failure() -> None:
    from vnpy_router.providers.concepts import BrokerConceptProvider

    class FakeXtData:
        def get_sector_list(self):
            return ["机器人概念", "上证A股"]

        def get_stock_list_in_sector(self, sector_name):
            if sector_name == "机器人概念":
                return ["SH603112", "SZ002048"]
            return []

    provider = BrokerConceptProvider(xtdata=FakeXtData())

    boards = provider.list_boards("concept")
    assert [board.board_name for board in boards] == ["机器人概念"]
    members = provider.list_members(boards[0])
    assert [member.vt_symbol for member in members] == ["603112.SSE", "002048.SZSE"]
    assert provider.degraded_reason == ""

    unavailable = BrokerConceptProvider(xtdata_loader=lambda: None)
    assert unavailable.list_boards("concept") == []
    assert "unavailable" in unavailable.degraded_reason


def test_akshare_concept_provider_maps_boards_and_members_from_fallback_source() -> None:
    from vnpy_router.providers.concepts import AkshareConceptProvider

    class FakeFrame:
        def __init__(self, rows):
            self.rows = rows

        def to_dict(self, orient):
            assert orient == "records"
            return self.rows

    class FakeAkshare:
        def stock_board_concept_name_em(self):
            return FakeFrame([{"板块代码": "BK1001", "板块名称": "机器人概念"}])

        def stock_board_concept_cons_em(self, symbol):
            assert symbol == "机器人概念"
            return FakeFrame([{"代码": "603112", "名称": "华翔股份"}])

    provider = AkshareConceptProvider(akshare=FakeAkshare())

    boards = provider.list_boards("concept")
    assert boards[0].board_id == "akshare:concept:BK1001"
    members = provider.list_members(boards[0])
    assert [(member.vt_symbol, member.name) for member in members] == [
        ("603112.SSE", "华翔股份")
    ]
