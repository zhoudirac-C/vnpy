"""
Security master and alias catalog for news entity resolution.
"""

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SecurityEntity:
    """
    One tradable security in vn.py vt_symbol format.
    """

    vt_symbol: str
    symbol: str
    exchange: str
    name: str
    short_name: str
    industry: str = ""
    sector: str = ""
    concept_tags: tuple[str, ...] = ()
    provider_name: str = "local_security_catalog"
    provider_version: str = ""


@dataclass(frozen=True)
class SecurityAlias:
    """
    One searchable alias for a security.
    """

    alias: str
    vt_symbol: str
    alias_type: str = "alias"
    confidence: float = 0.8
    is_ambiguous: bool = False
    provider_name: str = "local_security_catalog"
    provider_version: str = ""


@dataclass(frozen=True)
class AliasLookup:
    """
    Alias lookup result preserving all matches for ambiguity checks.
    """

    alias: str
    matches: tuple[SecurityAlias, ...]

    @property
    def is_ambiguous(self) -> bool:
        """
        Return whether this alias maps to multiple securities.
        """
        symbols = {match.vt_symbol for match in self.matches}
        return len(symbols) > 1 or any(match.is_ambiguous for match in self.matches)


@dataclass
class SecurityEntityCatalog:
    """
    In-memory security master used by deterministic entity resolution.
    """

    entities: dict[str, SecurityEntity] = field(default_factory=dict)
    aliases: dict[str, list[SecurityAlias]] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> "SecurityEntityCatalog":
        """
        Build an empty catalog.
        """
        return cls()

    @classmethod
    def from_path(cls, path: str | Path) -> "SecurityEntityCatalog":
        """
        Load a security catalog from CSV or JSON.
        """
        source = Path(path)
        if not source.exists():
            raise FileNotFoundError(source)
        if source.suffix.lower() == ".json":
            rows = json.loads(source.read_text(encoding="utf-8"))
            if not isinstance(rows, list):
                raise ValueError("security catalog JSON must contain a list")
            return cls.from_rows(rows)

        with source.open("r", encoding="utf-8", newline="") as f:
            return cls.from_rows(list(csv.DictReader(f)))

    @classmethod
    def from_rows(cls, rows: list[dict[str, Any]]) -> "SecurityEntityCatalog":
        """
        Build a catalog from mapping rows.
        """
        catalog = cls()
        for row in rows:
            entity = _entity_from_row(row)
            catalog.add_entity(entity)
            catalog.add_alias(SecurityAlias(entity.symbol, entity.vt_symbol, "code", 0.96))
            catalog.add_alias(SecurityAlias(entity.vt_symbol, entity.vt_symbol, "vt_symbol", 0.98))
            catalog.add_alias(SecurityAlias(entity.name, entity.vt_symbol, "name", 0.92))
            catalog.add_alias(SecurityAlias(entity.short_name, entity.vt_symbol, "short_name", 0.88))
            for alias in _split_tags(row.get("aliases", "")):
                catalog.add_alias(SecurityAlias(alias, entity.vt_symbol, "alias", 0.78))
        catalog.mark_ambiguous_aliases()
        return catalog

    def add_entity(self, entity: SecurityEntity) -> None:
        """
        Add or replace one entity.
        """
        if entity.vt_symbol:
            self.entities[entity.vt_symbol] = entity

    def add_alias(self, alias: SecurityAlias) -> None:
        """
        Add a searchable alias.
        """
        text = _normalize_alias(alias.alias)
        if not text or not alias.vt_symbol:
            return
        self.aliases.setdefault(text, []).append(alias)

    def mark_ambiguous_aliases(self) -> None:
        """
        Mark aliases shared by multiple securities.
        """
        for key, values in list(self.aliases.items()):
            if len({value.vt_symbol for value in values}) <= 1:
                continue
            self.aliases[key] = [
                SecurityAlias(
                    alias=value.alias,
                    vt_symbol=value.vt_symbol,
                    alias_type=value.alias_type,
                    confidence=value.confidence,
                    is_ambiguous=True,
                    provider_name=value.provider_name,
                    provider_version=value.provider_version,
                )
                for value in values
            ]

    def get(self, vt_symbol: str) -> SecurityEntity | None:
        """
        Return one entity by vt_symbol.
        """
        return self.entities.get(vt_symbol)

    def find_by_symbol(self, symbol: str) -> SecurityEntity | None:
        """
        Return one entity by raw symbol code.
        """
        text = symbol.strip().upper()
        if "." in text:
            return self.get(_normalize_vt_symbol(text))
        for entity in self.entities.values():
            if entity.symbol == text:
                return entity
        return None

    def lookup_alias(self, alias: str) -> AliasLookup | None:
        """
        Lookup an alias, preserving ambiguous matches.
        """
        text = _normalize_alias(alias)
        matches = self.aliases.get(text)
        if not matches:
            return None
        return AliasLookup(alias=alias, matches=tuple(matches))

    def searchable_aliases(self) -> list[AliasLookup]:
        """
        Return aliases ordered by length so longer names win before short aliases.
        """
        lookups = [
            AliasLookup(alias=key, matches=tuple(values))
            for key, values in self.aliases.items()
            if key
        ]
        return sorted(lookups, key=lambda item: len(item.alias), reverse=True)


def _entity_from_row(row: dict[str, Any]) -> SecurityEntity:
    """
    Convert one row into SecurityEntity.
    """
    vt_symbol = str(row.get("vt_symbol") or "").strip().upper()
    symbol = str(row.get("symbol") or "").strip().upper()
    exchange = str(row.get("exchange") or "").strip().upper()
    if not vt_symbol and symbol and exchange:
        vt_symbol = f"{symbol}.{exchange}"
    if not symbol and vt_symbol:
        symbol = vt_symbol.split(".", 1)[0]
    if not exchange and "." in vt_symbol:
        exchange = vt_symbol.split(".", 1)[1]

    return SecurityEntity(
        vt_symbol=vt_symbol,
        symbol=symbol,
        exchange=exchange,
        name=str(row.get("name") or "").strip(),
        short_name=str(row.get("short_name") or row.get("name") or "").strip(),
        industry=str(row.get("industry") or "").strip(),
        sector=str(row.get("sector") or "").strip(),
        concept_tags=tuple(_split_tags(row.get("concept_tags", ""))),
        provider_name=str(row.get("provider_name") or "local_security_catalog"),
        provider_version=str(row.get("provider_version") or ""),
    )


def _split_tags(value: Any) -> list[str]:
    """
    Split concept/alias fields from CSV/JSON values.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass
    for sep in ("|", ";", "，", ","):
        if sep in text:
            return [item.strip() for item in text.split(sep) if item.strip()]
    return [text]


def _normalize_alias(value: str) -> str:
    """
    Normalize alias text for deterministic matching.
    """
    return str(value or "").strip().upper()


def _normalize_vt_symbol(value: str) -> str:
    """
    Normalize common exchange suffixes to vn.py-style exchange codes.
    """
    text = value.strip().upper()
    if text.endswith(".SH"):
        return text[:-3] + ".SSE"
    if text.endswith(".SZ"):
        return text[:-3] + ".SZSE"
    if text.endswith(".BJ"):
        return text[:-3] + ".BSE"
    return text
