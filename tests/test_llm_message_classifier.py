from datetime import datetime
import json

from vnpy_router.event_storage import NewsRaw


def test_llm_message_classifier_uses_fast_and_deep_thinking_policy():
    """LLM message classifier should disable thinking for intraday/scheduled and enable it for research."""
    from vnpy_router.news_llm_classifier import LlmClassifierRuntimeConfig

    config = LlmClassifierRuntimeConfig(
        intraday_thinking_type="disabled",
        scheduled_thinking_type="disabled",
        research_thinking_type="enabled",
        replay_thinking_type="enabled",
        batch_thinking_type="enabled",
    )

    assert config.thinking_for_mode("intraday") == "disabled"
    assert config.thinking_for_mode("scheduled_ingestion") == "disabled"
    assert config.thinking_for_mode("research") == "enabled"
    assert config.thinking_for_mode("replay") == "enabled"
    assert config.thinking_for_mode("batch_industry_mapping") == "enabled"


def test_llm_message_classifier_validates_free_form_stock_links(tmp_path):
    """LLM can propose stocks freely, but only local security-master matches become links."""
    from vnpy_router.news_llm_classifier import LlmMessageClassifier, LlmClassifierRuntimeConfig
    from vnpy_router.security_catalog import SecurityEntityCatalog

    catalog_path = tmp_path / "securities.csv"
    catalog_path.write_text(
        "\n".join(
            [
                "vt_symbol,symbol,exchange,name,short_name,industry,sector,concept_tags,aliases",
                "600406.SSE,600406,SSE,国电南瑞科技股份有限公司,国电南瑞,电网设备,电力设备,特高压|电网智能化,",
                "000400.SZSE,000400,SZSE,许继电气股份有限公司,许继电气,电网设备,电力设备,特高压|储能PCS,",
            ]
        ),
        encoding="utf-8",
    )
    classifier = LlmMessageClassifier(
        catalog=SecurityEntityCatalog.from_path(catalog_path),
        client=FakeLlmClient(
            """
            {
              "event_type": "policy",
              "topics": ["新型电力系统", "特高压"],
              "impact_direction": "positive",
              "stocks": [
                {
                  "name": "国电南瑞",
                  "vt_symbol": "600406.SSE",
                  "confidence": 0.95,
                  "relation_type": "direct",
                  "reason": "电网智能化和特高压核心设备商",
                  "risk": "政策落地节奏不及预期"
                },
                {
                  "name": "幻觉电网",
                  "vt_symbol": "999999.SSE",
                  "confidence": 0.91,
                  "relation_type": "theme",
                  "reason": "不存在的股票",
                  "risk": "幻觉"
                }
              ],
              "limitations": ["无候选池可能误配"]
            }
            """
        ),
        config=LlmClassifierRuntimeConfig(model="glm-4.7"),
    )
    news = NewsRaw(
        source="gdelt",
        url="https://example.test/policy",
        title="新型电力系统政策推动特高压和电网智能化",
        content="特高压、电网智能化、储能调峰和新能源消纳受益。",
        published_at=datetime(2024, 1, 2),
        provider_name="gdelt_global_news",
        source_quality="global_public_news",
        trust_score=0.65,
    )

    result = classifier.classify_and_link(news, mode="scheduled_ingestion")

    assert classifier.client.calls[0]["model"] == "glm-4.7"
    assert classifier.client.calls[0]["thinking_type"] == "disabled"
    assert result.event_type == "policy"
    assert result.impact_direction == "positive"
    assert [link.vt_symbol for link in result.links] == ["600406.SSE"]
    assert result.links[0].link_reason == "llm_industry_linker"
    assert result.links[0].confidence == 0.95
    assert "999999.SSE" in result.dropped_symbols


def test_ingestion_job_uses_llm_classifier_for_industry_news_without_direct_symbol(tmp_path):
    """Industry messages without explicit stocks should use optional LLM classifier to create event links."""
    from vnpy_router.news_llm_classifier import LlmMessageClassifier, LlmClassifierRuntimeConfig
    from vnpy_router.providers.news_external import FetchedNews, NewsFetchResult
    from vnpy_router.security_catalog import SecurityEntityCatalog
    from vnpy_tradingagents.news_ingestion import ExternalNewsIngestionJob

    catalog_path = tmp_path / "securities.csv"
    catalog_path.write_text(
        "\n".join(
            [
                "vt_symbol,symbol,exchange,name,short_name,industry,sector,concept_tags,aliases",
                "600406.SSE,600406,SSE,国电南瑞科技股份有限公司,国电南瑞,电网设备,电力设备,特高压|电网智能化,",
            ]
        ),
        encoding="utf-8",
    )
    news = NewsRaw(
        source="policy",
        url="https://example.test/policy",
        title="电网行业政策加快特高压和智能化建设",
        content="行业政策利好特高压、电网智能化。",
        published_at=datetime(2024, 1, 2),
        provider_name="local_policy",
        source_quality="manual",
        trust_score=0.8,
    )
    llm_classifier = LlmMessageClassifier(
        catalog=SecurityEntityCatalog.from_path(catalog_path),
        client=FakeLlmClient(
            """
            {
              "event_type": "industry",
              "topics": ["特高压", "电网智能化"],
              "impact_direction": "positive",
              "stocks": [
                {
                  "name": "国电南瑞",
                  "vt_symbol": "600406.SSE",
                  "confidence": 0.93,
                  "relation_type": "direct",
                  "reason": "电网自动化核心公司",
                  "risk": "订单节奏波动"
                }
              ],
              "limitations": []
            }
            """
        ),
        config=LlmClassifierRuntimeConfig(scheduled_thinking_type="disabled"),
    )
    storage = MemoryEventStorage()
    job = ExternalNewsIngestionJob(
        provider=FakeExternalProvider(NewsFetchResult(items=[FetchedNews(news)])),
        storage=storage,
        llm_classifier=llm_classifier,
        llm_mode="scheduled_ingestion",
        clock=lambda: datetime(2024, 1, 3),
    )

    summary = job.run(["600406.SSE"], datetime(2024, 1, 1), datetime(2024, 1, 3))

    assert summary.event_count == 1
    assert storage.news_events[0].vt_symbol == "600406.SSE"
    assert storage.news_events[0].event_type == "industry"
    assert storage.event_symbol_links[0].link_reason == "llm_industry_linker"
    assert storage.event_symbol_links[0].confidence == 0.93
    assert llm_classifier.client.calls[0]["thinking_type"] == "disabled"


def test_llm_classifier_settings_and_readiness_require_key_and_catalog(tmp_path):
    """UI settings and readiness should explain the optional LLM classifier prerequisites."""
    from vnpy.trader.setting import SETTINGS
    from vnpy.trader.ui.widget import SETTING_HELP_TEXT
    from vnpy_tradingagents.readiness import ProductionReadinessChecker, ReadinessStatus

    assert SETTINGS["news.llm_classifier.enabled"] is False
    assert SETTINGS["news.llm_classifier.model"] == "glm-4.7"
    assert SETTINGS["news.llm_classifier.fast_timeout_seconds"] == 360
    assert SETTINGS["news.llm_classifier.deep_timeout_seconds"] == 2700
    assert "ZHIPU_API_KEY" in SETTING_HELP_TEXT["news.llm_classifier.api_key_env_var"]
    assert "默认 disabled" in SETTING_HELP_TEXT["news.llm_classifier.scheduled_thinking_type"]
    assert "默认 enabled" in SETTING_HELP_TEXT["news.llm_classifier.research_thinking_type"]
    assert "360 秒" in SETTING_HELP_TEXT["news.llm_classifier.fast_timeout_seconds"]
    assert "45 分钟" in SETTING_HELP_TEXT["news.llm_classifier.deep_timeout_seconds"]

    report = ProductionReadinessChecker(
        settings={
            "database.name": "postgresql",
            "database.host": "localhost",
            "database.port": 5432,
            "database.database": "vnpy",
            "database.user": "postgres",
            "database.password": "secret",
            "router.providers": "local_file",
            "router.local_path": str(tmp_path),
            "tradingagents.api_key_env_var": "OPENAI_API_KEY",
            "tradingagents.worker_factory": "vnpy_tradingagents.tradingagents_factory:build",
            "news.ingestion.enabled": True,
            "news.ingestion.providers": "local_file",
            "news.ingestion.local_path": str(tmp_path),
            "news.llm_classifier.enabled": True,
            "news.llm_classifier.api_key_env_var": "ZHIPU_API_KEY",
            "news.entity.catalog_path": "",
        },
        environ={"OPENAI_API_KEY": "llm-key"},
        module_available=lambda name: name in {"peewee", "psycopg2", "vnpy_tradingagents.tradingagents_factory"},
        path_exists=lambda path: True,
    ).check()

    item = report.by_name("news_ingestion")
    assert item.status == ReadinessStatus.WARNING
    assert "ZHIPU_API_KEY" in item.message
    assert "news.entity.catalog_path" in item.message


def test_zhipu_glm_chat_client_records_usage(monkeypatch):
    """Real GLM client should keep response usage for smoke/audit logging."""
    from vnpy_router import news_llm_classifier as module
    from vnpy_router.news_llm_classifier import ZhipuGlmChatClient

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [{"message": {"content": "{\"ok\": true}"}}],
                    "usage": {
                        "prompt_tokens": 12,
                        "completion_tokens": 8,
                        "total_tokens": 20,
                    },
                }
            ).encode("utf-8")

    monkeypatch.setattr(module, "urlopen", lambda request, timeout: FakeResponse())

    client = ZhipuGlmChatClient(api_key="secret")
    content = client.complete(
        messages=[{"role": "user", "content": "hi"}],
        model="glm-4.7",
        thinking_type="disabled",
        timeout_seconds=10,
    )

    assert content == "{\"ok\": true}"
    assert client.last_usage == {
        "prompt_tokens": 12,
        "completion_tokens": 8,
        "total_tokens": 20,
    }


class FakeLlmClient:
    """Tiny fake LLM client."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = []

    def complete(self, messages, model, thinking_type, timeout_seconds):
        self.calls.append(
            {
                "messages": messages,
                "model": model,
                "thinking_type": thinking_type,
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.content


class FakeExternalProvider:
    """External provider fake returning a prebuilt result."""

    def __init__(self, result) -> None:
        self.result = result

    def fetch(self, request, output=print):
        return self.result


class MemoryEventStorage:
    """In-memory event storage fake."""

    def __init__(self) -> None:
        self.raw_news = []
        self.news_events = []
        self.event_symbol_links = []
        self.quality_reports = []

    def save_news_raw(self, news) -> None:
        self.raw_news.append(news)

    def save_news_event(self, event) -> None:
        self.news_events.append(event)

    def save_event_symbol_link(self, link) -> None:
        self.event_symbol_links.append(link)

    def save_event_quality_report(self, report) -> None:
        self.quality_reports.append(report)
