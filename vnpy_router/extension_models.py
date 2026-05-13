"""
Peewee models for vnpy_router extension tables.
"""

from typing import Any


ROUTER_EXTENSION_TABLE_NAMES: tuple[str, ...] = (
    "market_bar_snapshot",
    "fundamental_snapshot",
    "valuation_snapshot",
    "industry_snapshot",
    "benchmark_snapshot",
    "portfolio_snapshot",
    "alpha_factor_snapshot",
    "news_raw",
    "news_event",
    "social_post_raw",
    "sentiment_snapshot",
    "event_symbol_link",
    "event_quality_report",
    "security_entity",
    "security_alias",
    "concept_board",
    "concept_board_member",
    "security_concept_link",
    "financial_statement_snapshot",
    "financial_indicator_snapshot",
    "financial_report_document",
)


def build_router_extension_models(database: Any) -> list[type]:
    """
    Build Peewee models bound to the provided database.
    """
    from peewee import (
        CompositeKey,
        BooleanField,
        DateTimeField,
        FloatField,
        IntegerField,
        Model,
        SQL,
        TextField,
    )
    from playhouse.postgres_ext import BinaryJSONField

    peewee_database = database

    class BaseExtensionModel(Model):
        class Meta:
            database = peewee_database
            legacy_table_names = False

    class MarketBarSnapshot(BaseExtensionModel):
        vt_symbol = TextField()
        symbol = TextField()
        exchange = TextField()
        interval = TextField()
        datetime = DateTimeField()
        open_price = FloatField()
        high_price = FloatField()
        low_price = FloatField()
        close_price = FloatField()
        volume = FloatField()
        turnover = FloatField()
        open_interest = FloatField()
        provider_name = TextField()
        provider_endpoint = TextField(null=True)
        provider_version = TextField(null=True)
        adjustment = TextField(null=True)
        pulled_at = DateTimeField(constraints=[SQL("DEFAULT now()")], null=True)
        quality_status = TextField(null=True)
        quality_report_id = TextField(null=True)

        class Meta:
            table_name = "market_bar_snapshot"
            primary_key = CompositeKey("vt_symbol", "interval", "datetime", "provider_name")

    class PayloadSnapshot(BaseExtensionModel):
        vt_symbol = TextField()
        as_of = DateTimeField()
        provider_name = TextField()
        provider_version = TextField(null=True)
        pulled_at = DateTimeField(constraints=[SQL("DEFAULT now()")], null=True)
        quality_status = TextField(null=True)
        payload = BinaryJSONField()

        class Meta:
            primary_key = CompositeKey("vt_symbol", "as_of", "provider_name")

    class FundamentalSnapshot(PayloadSnapshot):
        class Meta:
            table_name = "fundamental_snapshot"
            primary_key = CompositeKey("vt_symbol", "as_of", "provider_name")

    class ValuationSnapshot(PayloadSnapshot):
        class Meta:
            table_name = "valuation_snapshot"
            primary_key = CompositeKey("vt_symbol", "as_of", "provider_name")

    class IndustrySnapshot(PayloadSnapshot):
        class Meta:
            table_name = "industry_snapshot"
            primary_key = CompositeKey("vt_symbol", "as_of", "provider_name")

    class BenchmarkSnapshot(PayloadSnapshot):
        class Meta:
            table_name = "benchmark_snapshot"
            primary_key = CompositeKey("vt_symbol", "as_of", "provider_name")

    class PortfolioSnapshot(PayloadSnapshot):
        class Meta:
            table_name = "portfolio_snapshot"
            primary_key = CompositeKey("vt_symbol", "as_of", "provider_name")

    class AlphaFactorSnapshot(PayloadSnapshot):
        class Meta:
            table_name = "alpha_factor_snapshot"
            primary_key = CompositeKey("vt_symbol", "as_of", "provider_name")

    class NewsRaw(BaseExtensionModel):
        raw_hash = TextField(primary_key=True)
        source = TextField()
        url = TextField(null=True)
        title = TextField()
        content = TextField()
        published_at = DateTimeField(null=True)
        provider_name = TextField()
        provider_version = TextField(null=True)
        source_quality = TextField(null=True)
        trust_score = FloatField(null=True)
        relevance_score = FloatField(null=True)
        spam_score = FloatField(null=True)
        cluster_id = TextField(null=True)
        dedup_window_seconds = IntegerField(null=True)
        review_status = TextField(null=True)
        pulled_at = DateTimeField(constraints=[SQL("DEFAULT now()")], null=True)
        raw_payload = BinaryJSONField(null=True)

        class Meta:
            table_name = "news_raw"

    class NewsEvent(BaseExtensionModel):
        event_id = TextField(primary_key=True)
        vt_symbol = TextField()
        title = TextField()
        summary = TextField()
        event_type = TextField()
        occurred_at = DateTimeField()
        source = TextField()
        url = TextField(null=True)
        provider_name = TextField()
        provider_version = TextField(null=True)
        raw_hash = TextField(null=True)
        source_quality = TextField(null=True)
        trust_score = FloatField(null=True)
        relevance_score = FloatField(null=True)
        spam_score = FloatField(null=True)
        cluster_id = TextField(null=True)
        dedup_window_seconds = IntegerField(null=True)
        review_status = TextField(null=True)
        pulled_at = DateTimeField(constraints=[SQL("DEFAULT now()")], null=True)

        class Meta:
            table_name = "news_event"

    class SocialPostRaw(BaseExtensionModel):
        raw_hash = TextField(primary_key=True)
        source = TextField()
        author = TextField(null=True)
        url = TextField(null=True)
        content = TextField()
        published_at = DateTimeField(null=True)
        provider_name = TextField()
        provider_version = TextField(null=True)
        source_quality = TextField(null=True)
        trust_score = FloatField(null=True)
        spam_score = FloatField(null=True)
        dedup_window_seconds = IntegerField(null=True)
        review_status = TextField(null=True)
        pulled_at = DateTimeField(constraints=[SQL("DEFAULT now()")], null=True)
        raw_payload = BinaryJSONField(null=True)

        class Meta:
            table_name = "social_post_raw"

    class SentimentSnapshot(BaseExtensionModel):
        vt_symbol = TextField()
        as_of = DateTimeField()
        provider_name = TextField()
        provider_version = TextField(null=True)
        payload = BinaryJSONField()
        pulled_at = DateTimeField(constraints=[SQL("DEFAULT now()")], null=True)

        class Meta:
            table_name = "sentiment_snapshot"
            primary_key = CompositeKey("vt_symbol", "as_of", "provider_name")

    class EventSymbolLink(BaseExtensionModel):
        event_id = TextField()
        vt_symbol = TextField()
        sector = TextField(null=True)
        topic = TextField(null=True)
        confidence = FloatField(null=True)
        relevance_score = FloatField(null=True)
        link_reason = TextField(null=True)
        provider_name = TextField()
        provider_version = TextField(null=True)
        pulled_at = DateTimeField(constraints=[SQL("DEFAULT now()")], null=True)

        class Meta:
            table_name = "event_symbol_link"
            primary_key = CompositeKey("event_id", "vt_symbol")

    class EventQualityReport(BaseExtensionModel):
        report_id = TextField(primary_key=True)
        source = TextField()
        provider_name = TextField()
        as_of = DateTimeField()
        source_quality = TextField()
        trust_score = FloatField(null=True)
        spam_score = FloatField(null=True)
        duplicate_count = IntegerField(default=0)
        reviewed_count = IntegerField(default=0)
        blocked_count = IntegerField(default=0)
        payload = BinaryJSONField(null=True)
        pulled_at = DateTimeField(constraints=[SQL("DEFAULT now()")], null=True)

        class Meta:
            table_name = "event_quality_report"

    class SecurityEntity(BaseExtensionModel):
        vt_symbol = TextField(primary_key=True)
        symbol = TextField()
        exchange = TextField()
        name = TextField()
        short_name = TextField(null=True)
        industry = TextField(null=True)
        sector = TextField(null=True)
        concept_tags = BinaryJSONField(null=True, index=False)
        provider_name = TextField()
        provider_version = TextField(null=True)
        updated_at = DateTimeField(null=True)

        class Meta:
            table_name = "security_entity"

    class SecurityAlias(BaseExtensionModel):
        alias = TextField()
        vt_symbol = TextField()
        alias_type = TextField(null=True)
        confidence = FloatField(null=True)
        is_ambiguous = BooleanField(default=False)
        provider_name = TextField()
        provider_version = TextField(null=True)
        updated_at = DateTimeField(constraints=[SQL("DEFAULT now()")], null=True)

        class Meta:
            table_name = "security_alias"
            primary_key = CompositeKey("alias", "vt_symbol")

    class ConceptBoard(BaseExtensionModel):
        board_id = TextField(primary_key=True)
        board_type = TextField()
        board_code = TextField()
        board_name = TextField()
        provider_name = TextField()
        provider_version = TextField(null=True)
        updated_at = DateTimeField(null=True)

        class Meta:
            table_name = "concept_board"

    class ConceptBoardMember(BaseExtensionModel):
        board_id = TextField()
        vt_symbol = TextField()
        symbol = TextField()
        exchange = TextField()
        name = TextField(null=True)
        rank = IntegerField(default=0)
        provider_name = TextField()
        provider_version = TextField(null=True)
        updated_at = DateTimeField(null=True)

        class Meta:
            table_name = "concept_board_member"
            primary_key = CompositeKey("board_id", "vt_symbol", "provider_name")

    class SecurityConceptLink(BaseExtensionModel):
        vt_symbol = TextField()
        board_id = TextField()
        board_name = TextField()
        board_type = TextField()
        relevance_score = FloatField(null=True)
        is_primary = BooleanField(default=False)
        provider_name = TextField()
        provider_version = TextField(null=True)
        updated_at = DateTimeField(null=True)

        class Meta:
            table_name = "security_concept_link"
            primary_key = CompositeKey("vt_symbol", "board_id", "provider_name")

    class FinancialStatementSnapshot(BaseExtensionModel):
        vt_symbol = TextField()
        report_period = DateTimeField()
        statement_type = TextField()
        report_type = TextField()
        announcement_date = DateTimeField()
        provider_name = TextField()
        provider_version = TextField(null=True)
        currency = TextField(default="CNY")
        unit = TextField(default="yuan")
        payload = BinaryJSONField()
        source_document_id = TextField(null=True)
        quality_status = TextField(null=True)
        quality_report = BinaryJSONField(null=True)
        pulled_at = DateTimeField(constraints=[SQL("DEFAULT now()")], null=True)

        class Meta:
            table_name = "financial_statement_snapshot"
            primary_key = CompositeKey(
                "vt_symbol",
                "report_period",
                "statement_type",
                "provider_name",
            )

    class FinancialIndicatorSnapshot(BaseExtensionModel):
        vt_symbol = TextField()
        report_period = DateTimeField()
        announcement_date = DateTimeField()
        provider_name = TextField()
        provider_version = TextField(null=True)
        payload = BinaryJSONField()
        quality_status = TextField(null=True)
        quality_report = BinaryJSONField(null=True)
        pulled_at = DateTimeField(constraints=[SQL("DEFAULT now()")], null=True)

        class Meta:
            table_name = "financial_indicator_snapshot"
            primary_key = CompositeKey("vt_symbol", "report_period", "provider_name")

    class FinancialReportDocument(BaseExtensionModel):
        document_id = TextField(primary_key=True)
        vt_symbol = TextField()
        report_period = DateTimeField()
        report_type = TextField()
        announcement_date = DateTimeField()
        title = TextField()
        source = TextField()
        provider_name = TextField()
        url = TextField(null=True)
        pdf_url = TextField(null=True)
        file_hash = TextField(null=True)
        provider_version = TextField(null=True)
        raw_payload = BinaryJSONField(null=True)
        pulled_at = DateTimeField(constraints=[SQL("DEFAULT now()")], null=True)

        class Meta:
            table_name = "financial_report_document"

    return [
        MarketBarSnapshot,
        FundamentalSnapshot,
        ValuationSnapshot,
        IndustrySnapshot,
        BenchmarkSnapshot,
        PortfolioSnapshot,
        AlphaFactorSnapshot,
        NewsRaw,
        NewsEvent,
        SocialPostRaw,
        SentimentSnapshot,
        EventSymbolLink,
        EventQualityReport,
        SecurityEntity,
        SecurityAlias,
        ConceptBoard,
        ConceptBoardMember,
        SecurityConceptLink,
        FinancialStatementSnapshot,
        FinancialIndicatorSnapshot,
        FinancialReportDocument,
    ]
