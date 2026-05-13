from __future__ import annotations


def test_concept_board_domain_normalizes_stock_links() -> None:
    from vnpy_router.concepts import (
        ConceptBoard,
        ConceptBoardMember,
        ConceptIngestionSummary,
        SecurityConceptLink,
        normalize_vt_symbol,
    )

    board = ConceptBoard(
        board_type="concept",
        board_code="BK1234",
        board_name="机器人概念",
        provider_name="broker_xt",
    )
    member = ConceptBoardMember(
        board_id=board.board_id,
        vt_symbol="sh603112",
        name="华翔股份",
        provider_name=board.provider_name,
        rank=1,
    )
    link = SecurityConceptLink.from_member(board, member, relevance_score=0.96)
    summary = ConceptIngestionSummary(
        provider_name="broker_xt",
        board_count=1,
        member_count=1,
        link_count=1,
        updated_symbols=("603112.SSE",),
    )

    assert board.board_id == "broker_xt:concept:BK1234"
    assert member.vt_symbol == "603112.SSE"
    assert member.symbol == "603112"
    assert member.exchange == "SSE"
    assert link.board_name == "机器人概念"
    assert link.is_primary is True
    assert normalize_vt_symbol("603112.sh") == "603112.SSE"
    assert summary.updated_symbols == ("603112.SSE",)
