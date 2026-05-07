from datetime import datetime

from vnpy_router.event_storage import NewsRaw


def test_p25_event_schema_and_peewee_models_include_entity_and_filtering_fields():
    """P25 storage should reuse extension tables for security entities and filter scores."""
    from peewee import SqliteDatabase

    from vnpy_router.event_storage import EVENT_SCHEMA
    from vnpy_router.extension_models import ROUTER_EXTENSION_TABLE_NAMES, build_router_extension_models

    assert "CREATE TABLE IF NOT EXISTS security_entity" in EVENT_SCHEMA
    assert "CREATE TABLE IF NOT EXISTS security_alias" in EVENT_SCHEMA
    assert "relevance_score DOUBLE PRECISION" in EVENT_SCHEMA
    assert "link_reason TEXT" in EVENT_SCHEMA

    models = {
        model._meta.table_name: model
        for model in build_router_extension_models(SqliteDatabase(":memory:"))
    }

    assert "security_entity" in ROUTER_EXTENSION_TABLE_NAMES
    assert "security_alias" in ROUTER_EXTENSION_TABLE_NAMES
    assert "security_entity" in models
    assert "security_alias" in models
    assert "relevance_score" in models["news_event"]._meta.fields
    assert "link_reason" in models["event_symbol_link"]._meta.fields


def test_security_catalog_resolves_code_name_alias_and_blocks_ambiguous_alias(tmp_path):
    """SecurityEntityResolver should link exact entities and avoid ambiguous aliases."""
    from vnpy_router.news_entity import SecurityEntityResolver
    from vnpy_router.security_catalog import SecurityEntityCatalog

    catalog_path = tmp_path / "securities.csv"
    catalog_path.write_text(
        "\n".join(
            [
                "vt_symbol,symbol,exchange,name,short_name,industry,sector,concept_tags,aliases",
                "600519.SSE,600519,SSE,贵州茅台酒股份有限公司,贵州茅台,白酒,消费,白酒|沪深300,茅台|Moutai",
                "000858.SZSE,000858,SZSE,宜宾五粮液股份有限公司,五粮液,白酒,消费,白酒|深证100,",
                "600030.SSE,600030,SSE,中信证券股份有限公司,中信证券,证券,金融,券商,中信",
                "601998.SSE,601998,SSE,中信银行股份有限公司,中信银行,银行,金融,银行,中信",
            ]
        ),
        encoding="utf-8",
    )

    catalog = SecurityEntityCatalog.from_path(catalog_path)
    resolver = SecurityEntityResolver(catalog)

    resolution = resolver.resolve(
        title="贵州茅台发布2024年年度报告",
        content="600519.SH 年报显示经营稳定。",
        payload={},
    )

    assert [link.vt_symbol for link in resolution.links] == ["600519.SSE"]
    assert resolution.links[0].confidence >= 0.9
    assert resolution.links[0].sector == "消费"
    assert "白酒" in resolution.links[0].topic

    multi_resolution = resolver.resolve(
        title="白酒行业景气改善，贵州茅台和五粮液受关注",
        content="贵州茅台、五粮液均被提及。",
        payload={},
    )

    assert {link.vt_symbol for link in multi_resolution.links} == {
        "600519.SSE",
        "000858.SZSE",
    }

    ambiguous_resolution = resolver.resolve(
        title="中信发布重要公告",
        content="简称中信存在多家公司歧义。",
        payload={},
    )

    assert ambiguous_resolution.links == []
    assert any("ambiguous" in warning for warning in ambiguous_resolution.warnings)


def test_classifier_quality_scorer_and_deduper_apply_production_news_rules():
    """Classification, scoring and dedup should prefer official disclosures."""
    from vnpy_router.news_classifier import EventClassifier
    from vnpy_router.news_dedup import NewsDeduper
    from vnpy_router.news_quality import NewsQualityScorer

    classifier = EventClassifier()
    scorer = NewsQualityScorer()
    deduper = NewsDeduper()

    official = NewsRaw(
        source="cninfo",
        url="https://static.cninfo.com.cn/finalpage/2024-01-02/notice.pdf",
        title="贵州茅台关于回购股份方案的公告",
        content="公司拟回购股份。",
        published_at=datetime(2024, 1, 2),
        provider_name="cninfo_announcement",
        source_quality="official_disclosure",
        trust_score=0.95,
        raw_payload={"secCode": "600519"},
    )
    sse_same = NewsRaw(
        source="sse",
        url="https://www.sse.com.cn/disclosure/listedinfo/announcement/notice.pdf",
        title="贵州茅台关于回购股份方案的公告",
        content="公司拟回购股份。",
        published_at=datetime(2024, 1, 2),
        provider_name="sse_announcement",
        source_quality="official_disclosure",
        trust_score=0.93,
        raw_payload={"SECURITY_CODE": "600519"},
    )
    akshare = NewsRaw(
        source="东方财富",
        url="https://example.test/news/1",
        title="贵州茅台回购消息",
        content="转载新闻。",
        published_at=datetime(2024, 1, 2),
        provider_name="akshare_stock_news",
        source_quality="public_web",
        trust_score=0.4,
    )

    assert classifier.classify(official) == "buyback"
    assert classifier.classify(
        NewsRaw(
            source="cninfo",
            url="https://static.cninfo.com.cn/finalpage/reg.pdf",
            title="关于收到上海证券交易所监管工作函的公告",
            content="监管工作函。",
            published_at=datetime(2024, 1, 2),
            provider_name="cninfo_announcement",
            source_quality="official_disclosure",
        )
    ) == "regulatory"
    assert classifier.classify(
        NewsRaw(
            source="gdelt",
            url="https://example.test/global",
            title="China exports face new tariff pressure",
            content="Global macro event.",
            published_at=datetime(2024, 1, 2),
            provider_name="gdelt_global_news",
            source_quality="global_public_news",
        )
    ) == "macro"

    official_score = scorer.score(official, link_confidence=0.98, event_type="buyback")
    akshare_score = scorer.score(akshare, link_confidence=0.80, event_type="buyback")

    assert official_score.review_status == "accepted"
    assert official_score.trust_score >= 0.9
    assert akshare_score.review_status == "pending"
    assert akshare_score.trust_score < 0.7

    assert deduper.register(official, vt_symbol="600519.SSE").is_duplicate is False
    duplicate = deduper.register(sse_same, vt_symbol="600519.SSE")
    assert duplicate.is_duplicate is True
    assert duplicate.cluster_id
