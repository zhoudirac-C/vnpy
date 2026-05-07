from types import SimpleNamespace


class FakeLayout:
    def __init__(self) -> None:
        self.inserted: list[object] = []

    def insertWidget(self, index: int, widget: object) -> None:
        self.inserted.insert(index, widget)


class FakeStrategy:
    def __init__(self, name: str) -> None:
        self.name = name

    def get_data(self) -> dict:
        return {
            "strategy_name": self.name,
            "vt_symbol": "600673.SSE",
            "class_name": "TestStrategy",
            "author": "test",
            "parameters": {},
            "variables": {"inited": False, "trading": False},
        }


class FakeStrategyManager:
    def __init__(self, cta_manager: object, cta_engine: object, data: dict) -> None:
        self.cta_manager = cta_manager
        self.cta_engine = cta_engine
        self.data = data
        self.parent = "alive"
        self.deleted = False

    def update_data(self, data: dict) -> None:
        self.data = data

    def setParent(self, parent: object) -> None:
        self.parent = parent

    def deleteLater(self) -> None:
        self.deleted = True


def test_sync_strategy_managers_adds_missing_strategy_cards() -> None:
    from vnpy_tradingagents.cta_ui_compat import sync_strategy_managers

    cta_engine = SimpleNamespace(strategies={"UI_AUTO": FakeStrategy("UI_AUTO")})
    manager = SimpleNamespace(
        cta_engine=cta_engine,
        managers={},
        scroll_layout=FakeLayout(),
        update_strategy_combo=lambda: None,
    )

    sync_strategy_managers(manager, FakeStrategyManager)

    assert "UI_AUTO" in manager.managers
    assert len(manager.scroll_layout.inserted) == 1
    assert manager.managers["UI_AUTO"].data["vt_symbol"] == "600673.SSE"


def test_sync_strategy_managers_removes_stale_strategy_cards() -> None:
    from vnpy_tradingagents.cta_ui_compat import sync_strategy_managers

    stale = FakeStrategyManager(None, None, {"strategy_name": "STALE"})
    manager = SimpleNamespace(
        cta_engine=SimpleNamespace(strategies={}),
        managers={"STALE": stale},
        scroll_layout=FakeLayout(),
        update_strategy_combo=lambda: None,
    )

    sync_strategy_managers(manager, FakeStrategyManager)

    assert manager.managers == {}
    assert stale.parent is None
    assert stale.deleted
