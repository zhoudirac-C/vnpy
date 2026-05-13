"""
Concept board domain objects and provider protocol.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ConceptBoard:
    """
    One industry or concept board from a market data provider.
    """

    board_type: str
    board_code: str
    board_name: str
    provider_name: str
    provider_version: str = ""
    board_id: str = ""
    updated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        board_type = str(self.board_type or "").strip().lower()
        if board_type not in {"concept", "industry"}:
            raise ValueError(f"unsupported board_type: {self.board_type}")
        board_code = str(self.board_code or self.board_name or "").strip()
        board_name = str(self.board_name or "").strip()
        provider_name = str(self.provider_name or "").strip()
        if not board_code or not board_name or not provider_name:
            raise ValueError("board_code, board_name and provider_name are required")
        object.__setattr__(self, "board_type", board_type)
        object.__setattr__(self, "board_code", board_code)
        object.__setattr__(self, "board_name", board_name)
        object.__setattr__(self, "provider_name", provider_name)
        if not self.board_id:
            object.__setattr__(self, "board_id", f"{provider_name}:{board_type}:{board_code}")


@dataclass(frozen=True)
class ConceptBoardMember:
    """
    One stock member of a concept or industry board.
    """

    board_id: str
    vt_symbol: str
    name: str
    provider_name: str
    rank: int = 0
    provider_version: str = ""
    updated_at: datetime = field(default_factory=datetime.now)
    symbol: str = ""
    exchange: str = ""

    def __post_init__(self) -> None:
        vt_symbol = normalize_vt_symbol(self.vt_symbol)
        if not self.board_id or not vt_symbol or not self.provider_name:
            raise ValueError("board_id, vt_symbol and provider_name are required")
        symbol, exchange = vt_symbol.split(".", 1)
        object.__setattr__(self, "vt_symbol", vt_symbol)
        object.__setattr__(self, "symbol", self.symbol or symbol)
        object.__setattr__(self, "exchange", self.exchange or exchange)


@dataclass(frozen=True)
class SecurityConceptLink:
    """
    Normalized stock-to-board relation.
    """

    vt_symbol: str
    board_id: str
    board_name: str
    board_type: str
    provider_name: str
    relevance_score: float = 1.0
    is_primary: bool = False
    provider_version: str = ""
    updated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "vt_symbol", normalize_vt_symbol(self.vt_symbol))

    @classmethod
    def from_member(
        cls,
        board: ConceptBoard,
        member: ConceptBoardMember,
        relevance_score: float = 1.0,
        is_primary: bool = True,
    ) -> "SecurityConceptLink":
        return cls(
            vt_symbol=member.vt_symbol,
            board_id=board.board_id,
            board_name=board.board_name,
            board_type=board.board_type,
            relevance_score=relevance_score,
            is_primary=is_primary,
            provider_name=member.provider_name,
            provider_version=member.provider_version or board.provider_version,
            updated_at=max(board.updated_at, member.updated_at),
        )


@dataclass(frozen=True)
class ConceptIngestionSummary:
    """
    Result summary for one concept board ingestion run.
    """

    provider_name: str
    board_count: int = 0
    member_count: int = 0
    link_count: int = 0
    updated_symbols: tuple[str, ...] = ()
    degraded_sources: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


class ConceptBoardProvider(Protocol):
    """
    Provider protocol for concept/industry boards and their members.
    """

    provider_name: str

    def list_boards(self, board_type: str = "concept") -> Sequence[ConceptBoard]:
        pass

    def list_members(self, board: ConceptBoard) -> Sequence[ConceptBoardMember]:
        pass


def normalize_vt_symbol(value: str) -> str:
    """
    Normalize common A-share code formats into vn.py vt_symbol.
    """
    text = str(value or "").strip().upper()
    if not text:
        return ""
    suffix = ""
    if "." in text:
        symbol, suffix = text.split(".", 1)
    elif text.startswith(("SH", "SZ", "BJ")):
        symbol = text[2:]
        suffix = text[:2]
    else:
        symbol = text
    symbol = symbol.zfill(6) if symbol.isdigit() and len(symbol) <= 6 else symbol
    exchange = _exchange_from_suffix(suffix) or _infer_exchange(symbol)
    if not symbol.isdigit() or len(symbol) != 6:
        return ""
    return f"{symbol}.{exchange}"


def _exchange_from_suffix(value: str) -> str:
    return {
        "SH": "SSE",
        "SSE": "SSE",
        "SZ": "SZSE",
        "SZSE": "SZSE",
        "BJ": "BSE",
        "BSE": "BSE",
    }.get(str(value or "").strip().upper(), "")


def _infer_exchange(symbol: str) -> str:
    if symbol.startswith(("6", "9")):
        return "SSE"
    if symbol.startswith(("8", "4")):
        return "BSE"
    return "SZSE"
