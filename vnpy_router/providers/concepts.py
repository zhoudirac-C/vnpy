"""
Concept board providers.

The seven-boll scanner only consumes normalized storage rows. Raw broker,
catalog and AKShare access is kept here so provider boundaries remain clear.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from vnpy_router.concepts import ConceptBoard, ConceptBoardMember, normalize_vt_symbol
from vnpy_router.security_catalog import SecurityEntityCatalog


class BrokerConceptProvider:
    """
    Best-effort concept provider using broker/QMT/XT sector APIs first.
    """

    provider_name: str = "broker_xt"

    def __init__(
        self,
        xtdata: Any | None = None,
        xtdata_loader: Callable[[], Any | None] | None = None,
    ) -> None:
        self._xtdata = xtdata
        self._xtdata_loader = xtdata_loader or _load_xtdata
        self.degraded_reason: str = ""

    def list_boards(self, board_type: str = "concept") -> Sequence[ConceptBoard]:
        """
        List available broker boards. Missing SDKs degrade to an empty list.
        """
        xtdata = self._get_xtdata()
        if xtdata is None:
            return []

        get_sector_list = getattr(xtdata, "get_sector_list", None)
        if not callable(get_sector_list):
            self.degraded_reason = "broker_xt_sector_list_unavailable"
            return []

        try:
            names = get_sector_list()
        except Exception as exc:
            self.degraded_reason = f"broker_xt_sector_list_failed:{exc}"
            return []

        boards: list[ConceptBoard] = []
        for name in _iter_text_values(names):
            if not _matches_board_type(name, board_type):
                continue
            boards.append(
                ConceptBoard(
                    board_type=board_type,
                    board_code=name,
                    board_name=name,
                    provider_name=self.provider_name,
                )
            )
        return boards

    def list_members(self, board: ConceptBoard) -> Sequence[ConceptBoardMember]:
        """
        List board members through ``xtdata.get_stock_list_in_sector``.
        """
        xtdata = self._get_xtdata()
        if xtdata is None:
            return []

        get_stock_list = getattr(xtdata, "get_stock_list_in_sector", None)
        if not callable(get_stock_list):
            self.degraded_reason = "broker_xt_sector_members_unavailable"
            return []

        try:
            raw_symbols = get_stock_list(board.board_name)
        except Exception as exc:
            self.degraded_reason = f"broker_xt_sector_members_failed:{exc}"
            return []

        members: list[ConceptBoardMember] = []
        for index, raw_symbol in enumerate(_iter_text_values(raw_symbols), start=1):
            vt_symbol = normalize_vt_symbol(raw_symbol)
            if not vt_symbol:
                continue
            members.append(
                ConceptBoardMember(
                    board_id=board.board_id,
                    vt_symbol=vt_symbol,
                    name="",
                    provider_name=self.provider_name,
                    rank=index,
                )
            )
        return members

    def _get_xtdata(self) -> Any | None:
        if self._xtdata is not None:
            self.degraded_reason = ""
            return self._xtdata
        try:
            self._xtdata = self._xtdata_loader()
        except Exception as exc:
            self.degraded_reason = f"broker_xt_unavailable:{exc}"
            return None
        if self._xtdata is None:
            self.degraded_reason = "broker_xt_unavailable"
        else:
            self.degraded_reason = ""
        return self._xtdata


class LocalConceptCatalogProvider:
    """
    Build concept and industry boards from a local security catalog.
    """

    provider_name: str = "local_security_catalog"

    def __init__(self, catalog_path: str | Path | None = None, catalog: SecurityEntityCatalog | None = None) -> None:
        self.catalog_path = Path(catalog_path) if catalog_path else None
        self.catalog = catalog

    def list_boards(self, board_type: str = "concept") -> Sequence[ConceptBoard]:
        """
        Derive board names from ``concept_tags`` or ``industry`` fields.
        """
        catalog = self._catalog()
        board_names: dict[str, None] = {}
        for entity in catalog.entities.values():
            for name in _entity_board_names(entity, board_type):
                board_names.setdefault(name, None)

        return [
            ConceptBoard(
                board_type=board_type,
                board_code=name,
                board_name=name,
                provider_name=self.provider_name,
            )
            for name in board_names
        ]

    def list_members(self, board: ConceptBoard) -> Sequence[ConceptBoardMember]:
        """
        Return catalog entities that belong to one derived board.
        """
        catalog = self._catalog()
        members: list[ConceptBoardMember] = []
        for entity in sorted(catalog.entities.values(), key=lambda item: item.vt_symbol):
            if board.board_name not in _entity_board_names(entity, board.board_type):
                continue
            members.append(
                ConceptBoardMember(
                    board_id=board.board_id,
                    vt_symbol=entity.vt_symbol,
                    name=entity.short_name or entity.name,
                    provider_name=self.provider_name,
                    rank=len(members) + 1,
                )
            )
        return members

    def _catalog(self) -> SecurityEntityCatalog:
        if self.catalog is not None:
            return self.catalog
        if self.catalog_path is None:
            return SecurityEntityCatalog.empty()
        self.catalog = SecurityEntityCatalog.from_path(self.catalog_path)
        return self.catalog


class AkshareConceptProvider:
    """
    AKShare fallback concept provider.
    """

    provider_name: str = "akshare"

    def __init__(
        self,
        akshare: Any | None = None,
        akshare_loader: Callable[[], Any | None] | None = None,
    ) -> None:
        self._akshare = akshare
        self._akshare_loader = akshare_loader or _load_akshare
        self.degraded_reason: str = ""

    def list_boards(self, board_type: str = "concept") -> Sequence[ConceptBoard]:
        akshare = self._get_akshare()
        if akshare is None:
            return []

        endpoint_name = (
            "stock_board_industry_name_em"
            if board_type == "industry"
            else "stock_board_concept_name_em"
        )
        endpoint = getattr(akshare, endpoint_name, None)
        if not callable(endpoint):
            self.degraded_reason = f"akshare_endpoint_unavailable:{endpoint_name}"
            return []

        try:
            rows = _records(endpoint())
        except Exception as exc:
            self.degraded_reason = f"akshare_board_fetch_failed:{exc}"
            return []

        boards: list[ConceptBoard] = []
        for row in rows:
            board_name = _first_value(row, ("板块名称", "概念名称", "行业名称", "名称", "name"))
            board_code = _first_value(row, ("板块代码", "概念代码", "行业代码", "代码", "code")) or board_name
            if not board_name:
                continue
            boards.append(
                ConceptBoard(
                    board_type=board_type,
                    board_code=board_code,
                    board_name=board_name,
                    provider_name=self.provider_name,
                )
            )
        return boards

    def list_members(self, board: ConceptBoard) -> Sequence[ConceptBoardMember]:
        akshare = self._get_akshare()
        if akshare is None:
            return []

        endpoint_name = (
            "stock_board_industry_cons_em"
            if board.board_type == "industry"
            else "stock_board_concept_cons_em"
        )
        endpoint = getattr(akshare, endpoint_name, None)
        if not callable(endpoint):
            self.degraded_reason = f"akshare_endpoint_unavailable:{endpoint_name}"
            return []

        try:
            rows = _records(endpoint(symbol=board.board_name))
        except TypeError:
            rows = _records(endpoint(board.board_name))
        except Exception as exc:
            self.degraded_reason = f"akshare_member_fetch_failed:{exc}"
            return []

        members: list[ConceptBoardMember] = []
        for index, row in enumerate(rows, start=1):
            vt_symbol = normalize_vt_symbol(
                _first_value(row, ("代码", "股票代码", "证券代码", "symbol", "code"))
            )
            if not vt_symbol:
                continue
            members.append(
                ConceptBoardMember(
                    board_id=board.board_id,
                    vt_symbol=vt_symbol,
                    name=_first_value(row, ("名称", "股票名称", "name")),
                    provider_name=self.provider_name,
                    rank=index,
                )
            )
        return members

    def _get_akshare(self) -> Any | None:
        if self._akshare is not None:
            self.degraded_reason = ""
            return self._akshare
        try:
            self._akshare = self._akshare_loader()
        except Exception as exc:
            self.degraded_reason = f"akshare_unavailable:{exc}"
            return None
        if self._akshare is None:
            self.degraded_reason = "akshare_unavailable"
        else:
            self.degraded_reason = ""
        return self._akshare


def build_concept_providers(
    provider_names: Sequence[str],
    catalog_path: str | Path | None = None,
) -> list[Any]:
    """
    Build providers in configured priority order.
    """
    providers: list[Any] = []
    for name in provider_names:
        normalized = str(name or "").strip().lower()
        if normalized in {"broker", "broker_xt", "xt", "qmt"}:
            providers.append(BrokerConceptProvider())
        elif normalized in {"local", "local_catalog", "catalog", "local_security_catalog"}:
            providers.append(LocalConceptCatalogProvider(catalog_path))
        elif normalized == "akshare":
            providers.append(AkshareConceptProvider())
    return providers


def _load_xtdata() -> Any | None:
    try:
        from xtquant import xtdata
    except Exception:
        return None
    return xtdata


def _load_akshare() -> Any | None:
    try:
        import akshare
    except Exception:
        return None
    return akshare


def _iter_text_values(values: Any) -> Iterable[str]:
    if values is None:
        return []
    if isinstance(values, Mapping):
        values = values.values()
    if isinstance(values, str):
        return [values.strip()] if values.strip() else []
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text:
            result.append(text)
    return result


def _matches_board_type(name: str, board_type: str) -> bool:
    board_type = str(board_type or "").strip().lower()
    if board_type == "concept":
        return _is_concept_like(name)
    if board_type == "industry":
        return not _is_market_sector(name) and not _is_concept_like(name)
    return False


def _is_concept_like(name: str) -> bool:
    text = str(name or "").strip()
    if _is_market_sector(text):
        return False
    return any(token in text for token in ("概念", "题材", "专题", "主题"))


def _is_market_sector(name: str) -> bool:
    return any(token in str(name or "") for token in ("A股", "指数", "沪深", "上证", "深证", "创业板", "科创板"))


def _entity_board_names(entity: Any, board_type: str) -> tuple[str, ...]:
    if board_type == "industry":
        return tuple(dict.fromkeys([item for item in (entity.industry,) if item]))
    return tuple(dict.fromkeys(str(item).strip() for item in entity.concept_tags if str(item).strip()))


def _records(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if hasattr(value, "to_dict"):
        rows = value.to_dict("records")
        return [dict(row) for row in rows]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [dict(row) for row in value if isinstance(row, Mapping)]
    return []


def _first_value(row: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() != "nan":
            return text
    return ""
