"""
Data providers for vnpy_router.
"""

from .akshare import AkshareProvider
from .base import BaseProvider
from .local_file import LocalFileProvider


__all__ = ["AkshareProvider", "BaseProvider", "LocalFileProvider"]
