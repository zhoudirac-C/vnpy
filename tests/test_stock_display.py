def test_stock_display_resolver_prefers_contract_name() -> None:
    from vnpy_tradingagents.stock_display import StockDisplayResolver

    resolver = StockDisplayResolver(main_engine=FakeMainEngine())

    assert resolver.name_for("600519.SSE") == "贵州茅台"
    assert resolver.display("600519.SSE") == "600519.SSE 贵州茅台"
    assert resolver.display("000001.SZSE", "平安银行") == "000001.SZSE 平安银行"


def test_stock_display_resolver_reads_security_entity_database_fallback() -> None:
    from vnpy_tradingagents.stock_display import StockDisplayResolver

    resolver = StockDisplayResolver(database=FakeDatabase())

    assert resolver.name_for("603112.SSE") == "华翔股份"
    assert resolver.display("603112.SSE") == "603112.SSE 华翔股份"


class FakeContract:
    vt_symbol = "600519.SSE"
    name = "贵州茅台"


class FakeMainEngine:
    def get_contract(self, vt_symbol):
        if vt_symbol == "600519.SSE":
            return FakeContract()
        return None


class FakeDatabase:
    def __init__(self) -> None:
        self.db = FakePeeweeDatabase()


class FakePeeweeDatabase:
    param = "?"

    def execute_sql(self, sql, params):
        assert "FROM security_entity" in sql
        assert params == ("603112.SSE",)
        return FakeCursor(("华翔股份", "华翔股份"))


class FakeCursor:
    def __init__(self, row) -> None:
        self.row = row

    def fetchone(self):
        return self.row
