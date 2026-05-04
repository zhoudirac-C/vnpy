from importlib import import_module
from typing import Any

from .types import Segment, to_datetime


_LAZY_ATTRS: dict[str, tuple[str, str]] = {
    "AlphaDataset": (".template", "AlphaDataset"),
    "process_drop_na": (".processor", "process_drop_na"),
    "process_fill_na": (".processor", "process_fill_na"),
    "process_cs_norm": (".processor", "process_cs_norm"),
    "process_robust_zscore_norm": (".processor", "process_robust_zscore_norm"),
    "process_cs_rank_norm": (".processor", "process_cs_rank_norm"),
}


def __getattr__(name: str) -> Any:
    """Lazily load dataset helpers that require optional alpha dependencies."""
    if name not in _LAZY_ATTRS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = _LAZY_ATTRS[name]
    module = import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


__all__ = [
    "AlphaDataset",
    "Segment",
    "to_datetime",
    "process_drop_na",
    "process_fill_na",
    "process_cs_norm",
    "process_robust_zscore_norm",
    "process_cs_rank_norm"
]
