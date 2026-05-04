from importlib import import_module
from typing import Any

from .logger import logger
from .dataset.types import Segment, to_datetime


_LAZY_ATTRS: dict[str, tuple[str, str]] = {
    "AlphaDataset": (".dataset", "AlphaDataset"),
    "AlphaModel": (".model", "AlphaModel"),
    "AlphaStrategy": (".strategy", "AlphaStrategy"),
    "BacktestingEngine": (".strategy", "BacktestingEngine"),
    "AlphaLab": (".lab", "AlphaLab"),
}


def __getattr__(name: str) -> Any:
    """Lazily load alpha components with optional heavy dependencies."""
    if name not in _LAZY_ATTRS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = _LAZY_ATTRS[name]
    module = import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


__all__ = [
    "logger",
    "AlphaDataset",
    "Segment",
    "to_datetime",
    "AlphaModel",
    "AlphaStrategy",
    "BacktestingEngine",
    "AlphaLab"
]
