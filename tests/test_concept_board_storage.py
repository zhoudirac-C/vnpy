from __future__ import annotations

from peewee import SqliteDatabase


def test_concept_board_schema_and_storage_upserts_links() -> None:
    from vnpy_router.concept_storage import PeeweeConceptBoardRepository
    from vnpy_router.concepts import ConceptBoard, ConceptBoardMember
    from vnpy_router.extension_models import ROUTER_EXTENSION_TABLE_NAMES

    database = SqliteDatabase(":memory:")
    repository = PeeweeConceptBoardRepository(database)
    repository.create_schema()

    board_robot = ConceptBoard(
        board_type="concept",
        board_code="BKROBOT",
        board_name="机器人概念",
        provider_name="broker_xt",
    )
    board_pv = ConceptBoard(
        board_type="concept",
        board_code="BKPV",
        board_name="光伏概念",
        provider_name="broker_xt",
    )
    members = [
        ConceptBoardMember(
            board_id=board_robot.board_id,
            vt_symbol="603112.SSE",
            name="华翔股份",
            provider_name="broker_xt",
            rank=1,
        ),
        ConceptBoardMember(
            board_id=board_pv.board_id,
            vt_symbol="603112.SSE",
            name="华翔股份",
            provider_name="broker_xt",
            rank=2,
        ),
    ]

    summary = repository.save_snapshot(
        boards=[board_robot, board_pv],
        members=members,
        max_concepts_per_symbol=2,
    )

    assert "concept_board" in ROUTER_EXTENSION_TABLE_NAMES
    assert "concept_board_member" in ROUTER_EXTENSION_TABLE_NAMES
    assert "security_concept_link" in ROUTER_EXTENSION_TABLE_NAMES
    assert summary.board_count == 2
    assert summary.member_count == 2
    assert summary.link_count == 2
    assert repository.list_security_concepts("603112.SSE") == [
        "机器人概念",
        "光伏概念",
    ]
    entity = repository.get_security_entity("603112.SSE")
    assert entity is not None
    assert entity["name"] == "华翔股份"
    assert entity["concept_tags"] == ["机器人概念", "光伏概念"]
    assert set(database.get_tables()) >= {
        "concept_board",
        "concept_board_member",
        "security_concept_link",
        "security_entity",
    }
