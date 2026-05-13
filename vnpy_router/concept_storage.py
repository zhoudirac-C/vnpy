"""
Persistence helpers for concept boards and stock concept links.
"""

from __future__ import annotations

import json

from collections.abc import Sequence
from typing import Any

from .concepts import (
    ConceptBoard,
    ConceptBoardMember,
    ConceptIngestionSummary,
    SecurityConceptLink,
)
from .extension_models import build_router_extension_models


class PeeweeConceptBoardRepository:
    """
    Store concept boards, members and normalized stock concept links.
    """

    def __init__(self, database: Any) -> None:
        self.database = database
        models = {
            model._meta.table_name: model
            for model in build_router_extension_models(database)
        }
        self.board_model = models["concept_board"]
        self.member_model = models["concept_board_member"]
        self.link_model = models["security_concept_link"]
        self.security_model = models["security_entity"]

    def create_schema(self) -> None:
        """
        Create concept-related tables idempotently.
        """
        self.database.connect(reuse_if_open=True)
        self.database.create_tables(
            [
                self.security_model,
                self.board_model,
                self.member_model,
                self.link_model,
            ],
            safe=True,
        )

    def save_snapshot(
        self,
        boards: Sequence[ConceptBoard],
        members: Sequence[ConceptBoardMember],
        max_concepts_per_symbol: int = 3,
        provider_name: str = "",
    ) -> ConceptIngestionSummary:
        """
        Save one provider snapshot and update per-stock concept tags.
        """
        self.database.connect(reuse_if_open=True)
        board_map = {board.board_id: board for board in boards}
        for board in boards:
            self._upsert_board(board)

        links: list[SecurityConceptLink] = []
        members_by_symbol: dict[str, list[tuple[ConceptBoardMember, ConceptBoard]]] = {}
        for member in members:
            board = board_map.get(member.board_id)
            if board is None:
                continue
            self._upsert_member(member)
            members_by_symbol.setdefault(member.vt_symbol, []).append((member, board))

        for vt_symbol, symbol_members in members_by_symbol.items():
            ordered = sorted(symbol_members, key=lambda item: (item[0].rank or 999999, item[1].board_name))
            concept_tags: list[str] = []
            for index, item in enumerate(ordered):
                member, board = item
                link = SecurityConceptLink.from_member(
                    board,
                    member,
                    relevance_score=max(0.0, 1.0 - index * 0.05),
                    is_primary=index == 0,
                )
                self._upsert_link(link)
                links.append(link)
                if len(concept_tags) < max_concepts_per_symbol and board.board_name not in concept_tags:
                    concept_tags.append(board.board_name)
            first_member = ordered[0][0]
            self._upsert_security_entity(first_member, concept_tags, ordered[0][1])

        return ConceptIngestionSummary(
            provider_name=provider_name or (boards[0].provider_name if boards else ""),
            board_count=len(boards),
            member_count=len(members),
            link_count=len(links),
            updated_symbols=tuple(sorted(members_by_symbol)),
        )

    def list_security_concepts(self, vt_symbol: str, limit: int = 3) -> list[str]:
        """
        Return concept board names for one stock ordered by relevance.
        """
        rows = (
            self.link_model.select()
            .where(self.link_model.vt_symbol == vt_symbol)
            .order_by(self.link_model.is_primary.desc(), self.link_model.relevance_score.desc())
            .limit(limit)
        )
        return [row.board_name for row in rows]

    def get_security_entity(self, vt_symbol: str) -> dict[str, Any] | None:
        """
        Return one normalized security entity row.
        """
        row = self.security_model.select().where(self.security_model.vt_symbol == vt_symbol).first()
        if row is None:
            return None
        return {
            "vt_symbol": row.vt_symbol,
            "symbol": row.symbol,
            "exchange": row.exchange,
            "name": row.name,
            "short_name": row.short_name,
            "industry": row.industry,
            "sector": row.sector,
            "concept_tags": _json_list(row.concept_tags),
            "provider_name": row.provider_name,
            "provider_version": row.provider_version,
        }

    def _upsert_board(self, board: ConceptBoard) -> None:
        payload = {
            "board_id": board.board_id,
            "board_type": board.board_type,
            "board_code": board.board_code,
            "board_name": board.board_name,
            "provider_name": board.provider_name,
            "provider_version": board.provider_version,
            "updated_at": board.updated_at,
        }
        _upsert(self.board_model, payload, [self.board_model.board_id])

    def _upsert_member(self, member: ConceptBoardMember) -> None:
        payload = {
            "board_id": member.board_id,
            "vt_symbol": member.vt_symbol,
            "symbol": member.symbol,
            "exchange": member.exchange,
            "name": member.name,
            "rank": member.rank,
            "provider_name": member.provider_name,
            "provider_version": member.provider_version,
            "updated_at": member.updated_at,
        }
        _upsert(
            self.member_model,
            payload,
            [
                self.member_model.board_id,
                self.member_model.vt_symbol,
                self.member_model.provider_name,
            ],
        )

    def _upsert_link(self, link: SecurityConceptLink) -> None:
        payload = {
            "vt_symbol": link.vt_symbol,
            "board_id": link.board_id,
            "board_name": link.board_name,
            "board_type": link.board_type,
            "relevance_score": link.relevance_score,
            "is_primary": link.is_primary,
            "provider_name": link.provider_name,
            "provider_version": link.provider_version,
            "updated_at": link.updated_at,
        }
        _upsert(
            self.link_model,
            payload,
            [
                self.link_model.vt_symbol,
                self.link_model.board_id,
                self.link_model.provider_name,
            ],
        )

    def _upsert_security_entity(
        self,
        member: ConceptBoardMember,
        concept_tags: list[str],
        board: ConceptBoard,
    ) -> None:
        payload = {
            "vt_symbol": member.vt_symbol,
            "symbol": member.symbol,
            "exchange": member.exchange,
            "name": member.name or member.symbol,
            "short_name": member.name or member.symbol,
            "industry": board.board_name if board.board_type == "industry" else None,
            "sector": board.board_name if board.board_type == "industry" else None,
            "concept_tags": concept_tags,
            "provider_name": member.provider_name,
            "provider_version": member.provider_version,
            "updated_at": member.updated_at,
        }
        _upsert(self.security_model, payload, [self.security_model.vt_symbol])


def _upsert(model: Any, payload: dict[str, Any], conflict_target: list[Any]) -> None:
    update = {
        key: value
        for key, value in payload.items()
        if key not in {field.name for field in conflict_target}
    }
    model.insert(**payload).on_conflict(
        conflict_target=conflict_target,
        update=update,
    ).execute()


def _json_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        return _json_list(decoded)
    return [str(value)]
