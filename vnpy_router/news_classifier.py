"""
Rule-based news and announcement classifier.
"""

from vnpy_router.event_storage import NewsRaw


class EventClassifier:
    """
    Classify normalized raw news into stable event_type values.
    """

    def classify(self, news: NewsRaw) -> str:
        """
        Return one production event_type.
        """
        text = f"{news.title}\n{news.content}".lower()
        provider = news.provider_name.lower()
        payload_text = " ".join(str(value).lower() for value in news.raw_payload.values())
        full_text = f"{text}\n{payload_text}"

        if "gdelt" in provider:
            return "macro"
        if any(keyword in full_text for keyword in ("年报", "半年报", "季报", "业绩预告", "业绩快报", "年度报告")):
            return "earnings"
        if any(keyword in full_text for keyword in ("监管函", "问询函", "处罚", "立案", "警示函", "监管工作函")):
            return "regulatory"
        if "回购" in full_text:
            return "buyback"
        if any(keyword in full_text for keyword in ("减持", "增持", "股东变动", "权益变动")):
            return "holding_change"
        if any(keyword in full_text for keyword in ("行业", "产业链", "板块", "政策")):
            return "industry"
        if any(keyword in full_text for keyword in ("利率", "汇率", "关税", "地缘", "出口管制", "tariff", "exports")):
            return "macro"
        if "announcement" in provider or news.source_quality == "official_disclosure":
            return "announcement"
        return "news"
