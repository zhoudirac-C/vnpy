"""
Deterministic entity resolution for news and announcements.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from .security_catalog import SecurityEntity, SecurityEntityCatalog


CODE_PATTERN = re.compile(r"(?<!\d)(\d{6})(?:\.(SH|SZ|BJ|SSE|SZSE|BSE))?(?!\d)", re.IGNORECASE)


@dataclass(frozen=True)
class ResolvedEntityLink:
    """
    One high-confidence link between an event and a security.
    """

    vt_symbol: str
    confidence: float
    reason: str
    sector: str = ""
    topic: str = ""
    link_reason: str = ""


@dataclass(frozen=True)
class EntityResolution:
    """
    Entity resolution output with warnings for audit.
    """

    links: list[ResolvedEntityLink] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class SecurityEntityResolver:
    """
    Resolve stock names, symbols and aliases from news rows.
    """

    def __init__(self, catalog: SecurityEntityCatalog | None = None) -> None:
        """"""
        self.catalog: SecurityEntityCatalog = catalog or SecurityEntityCatalog.empty()

    def resolve(
        self,
        title: str,
        content: str = "",
        payload: dict[str, Any] | None = None,
    ) -> EntityResolution:
        """
        Resolve all non-ambiguous security links in the text/payload.
        """
        payload = payload or {}
        text = f"{title}\n{content}"
        links: dict[str, ResolvedEntityLink] = {}
        warnings: list[str] = []

        for entity in self._entities_from_payload(payload):
            _keep_best(links, _link_for_entity(entity, 0.98, "provider_payload_code"))

        for match in CODE_PATTERN.finditer(text):
            entity = self._entity_from_code(match.group(1), match.group(2))
            if entity:
                _keep_best(links, _link_for_entity(entity, 0.95, "text_code"))

        title_text = title.upper()
        all_text = text.upper()
        for lookup in self.catalog.searchable_aliases():
            alias = lookup.alias.upper()
            if alias not in all_text:
                continue
            if lookup.is_ambiguous:
                warnings.append(f"ambiguous alias ignored: {lookup.alias}")
                continue

            match = lookup.matches[0]
            entity = self.catalog.get(match.vt_symbol)
            if not entity:
                continue

            in_title = alias in title_text
            confidence = match.confidence
            if match.alias_type == "name":
                confidence = max(confidence, 0.92)
            elif match.alias_type == "short_name":
                confidence = max(confidence, 0.88 if in_title else 0.78)
            elif in_title:
                confidence = max(confidence, 0.82)
            _keep_best(links, _link_for_entity(entity, confidence, f"text_{match.alias_type}"))

        return EntityResolution(
            links=sorted(links.values(), key=lambda item: item.vt_symbol),
            warnings=warnings,
        )

    def _entities_from_payload(self, payload: dict[str, Any]) -> list[SecurityEntity]:
        """
        Extract explicit provider security codes.
        """
        result: list[SecurityEntity] = []
        for key in (
            "vt_symbol",
            "secCode",
            "securityCode",
            "SECURITY_CODE",
            "symbol",
            "code",
            "证券代码",
        ):
            value = payload.get(key)
            if value is None or not str(value).strip():
                continue
            entity = self._entity_from_code(str(value).strip(), None)
            if entity:
                result.append(entity)
        return result

    def _entity_from_code(self, symbol: str, suffix: str | None) -> SecurityEntity | None:
        """
        Resolve a code with optional exchange suffix.
        """
        clean_symbol = symbol.strip().upper()
        if "." in clean_symbol:
            return self.catalog.find_by_symbol(clean_symbol)
        if suffix:
            exchange = _suffix_to_exchange(suffix)
            entity = self.catalog.get(f"{clean_symbol}.{exchange}")
            if entity:
                return entity
        entity = self.catalog.find_by_symbol(clean_symbol)
        if entity:
            return entity
        exchange = _exchange_from_symbol(clean_symbol)
        return self.catalog.get(f"{clean_symbol}.{exchange}")


def _link_for_entity(entity: SecurityEntity, confidence: float, reason: str) -> ResolvedEntityLink:
    """
    Build a link candidate from security master data.
    """
    topics = [entity.industry, *entity.concept_tags]
    return ResolvedEntityLink(
        vt_symbol=entity.vt_symbol,
        confidence=confidence,
        reason=reason,
        sector=entity.sector,
        topic="|".join(topic for topic in topics if topic),
    )


def _keep_best(links: dict[str, ResolvedEntityLink], link: ResolvedEntityLink) -> None:
    """
    Keep only the highest confidence link per symbol.
    """
    existing = links.get(link.vt_symbol)
    if existing is None or link.confidence > existing.confidence:
        links[link.vt_symbol] = link


def _suffix_to_exchange(suffix: str) -> str:
    """
    Convert common suffixes to vn.py exchange names.
    """
    text = suffix.upper()
    return {
        "SH": "SSE",
        "SZ": "SZSE",
        "BJ": "BSE",
        "SSE": "SSE",
        "SZSE": "SZSE",
        "BSE": "BSE",
    }.get(text, text)


def _exchange_from_symbol(symbol: str) -> str:
    """
    Guess A-share exchange from raw code when no suffix is available.
    """
    if symbol.startswith(("6", "9")):
        return "SSE"
    if symbol.startswith(("8", "4")):
        return "BSE"
    return "SZSE"
