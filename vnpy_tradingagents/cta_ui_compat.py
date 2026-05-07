from __future__ import annotations

from typing import Any


def sync_strategy_managers(cta_manager: Any, strategy_manager_class: type[Any]) -> None:
    """
    Reconcile visible CTA strategy cards with CtaEngine.strategies.

    vn.py creates strategy cards from EVENT_CTA_STRATEGY. In local desktop use we
    also sync from engine state after add/open so a missed UI event does not leave
    a strategy written to JSON but invisible in the CTA window.
    """
    strategies: dict[str, Any] = cta_manager.cta_engine.strategies

    for strategy_name, manager in list(cta_manager.managers.items()):
        if strategy_name not in strategies:
            cta_manager.managers.pop(strategy_name, None)
            manager.setParent(None)
            manager.deleteLater()

    for strategy_name, strategy in strategies.items():
        data: dict = strategy.get_data()

        if strategy_name in cta_manager.managers:
            cta_manager.managers[strategy_name].update_data(data)
            continue

        manager = strategy_manager_class(cta_manager, cta_manager.cta_engine, data)
        cta_manager.scroll_layout.insertWidget(0, manager)
        cta_manager.managers[strategy_name] = manager

    cta_manager.update_strategy_combo()


def install_cta_strategy_ui_refresh_patch() -> None:
    """
    Patch vnpy_ctastrategy UI to refresh strategy cards from engine state.
    """
    try:
        from vnpy_ctastrategy.ui.widget import CtaManager, StrategyManager
    except ModuleNotFoundError:
        return

    if getattr(CtaManager, "_vnpy_strategy_sync_patch", False):
        return

    original_init = CtaManager.__init__
    original_add_strategy = CtaManager.add_strategy

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        sync_strategy_managers(self, StrategyManager)

    def patched_add_strategy(self: Any) -> None:
        original_add_strategy(self)
        sync_strategy_managers(self, StrategyManager)

    CtaManager.__init__ = patched_init
    CtaManager.add_strategy = patched_add_strategy
    CtaManager._vnpy_strategy_sync_patch = True
