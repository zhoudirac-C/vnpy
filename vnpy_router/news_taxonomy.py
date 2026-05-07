"""
Industry, sector and concept helpers for news enrichment.
"""

from dataclasses import dataclass

from .news_entity import ResolvedEntityLink
from .security_catalog import SecurityEntityCatalog


@dataclass(frozen=True)
class TaxonomyMatch:
    """
    One industry/sector/concept match from free text.
    """

    sector: str = ""
    topic: str = ""
    reason: str = ""


class IndustryConceptMapper:
    """
    Map text to known industry, sector and concept topics without forcing symbol links.
    """

    def __init__(self, catalog: SecurityEntityCatalog | None = None) -> None:
        """"""
        self.catalog: SecurityEntityCatalog = catalog or SecurityEntityCatalog.empty()

    def enrich_link(self, link: ResolvedEntityLink) -> ResolvedEntityLink:
        """
        Return link unchanged; entity resolver already carries catalog taxonomy.
        """
        return link

    def match_text(self, text: str) -> list[TaxonomyMatch]:
        """
        Find known sector/topic mentions in text.
        """
        result: list[TaxonomyMatch] = []
        seen: set[tuple[str, str]] = set()
        for entity in self.catalog.entities.values():
            for topic in (entity.industry, *entity.concept_tags):
                if topic and topic in text:
                    key = (entity.sector, topic)
                    if key not in seen:
                        result.append(TaxonomyMatch(entity.sector, topic, "text_topic"))
                        seen.add(key)
        return result
