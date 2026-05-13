"""
Stock display-name resolution helpers for TradingAgents UI.
"""

from __future__ import annotations

from typing import Any


class StockDisplayResolver:
    """
    Resolve human-readable stock names without changing vt_symbol keys.
    """

    def __init__(self, main_engine: Any | None = None, database: Any | None = None) -> None:
        self.main_engine = main_engine
        self.database = database
        self._cache: dict[str, str] = {}

    def name_for(self, vt_symbol: str) -> str:
        """
        Return the best available stock name for a vt_symbol.
        """
        normalized = str(vt_symbol or "").strip().upper()
        if not normalized:
            return ""
        if normalized in self._cache:
            return self._cache[normalized]

        name = self._name_from_contract(normalized) or self._name_from_database(normalized)
        self._cache[normalized] = name
        return name

    def display(self, vt_symbol: str, name: str = "") -> str:
        """
        Return ``vt_symbol name`` when a name can be resolved.
        """
        symbol = str(vt_symbol or "").strip()
        stock_name = str(name or "").strip() or self.name_for(symbol)
        return f"{symbol} {stock_name}" if symbol and stock_name else symbol or stock_name

    def _name_from_contract(self, vt_symbol: str) -> str:
        get_contract = getattr(self.main_engine, "get_contract", None)
        if not callable(get_contract):
            return ""
        try:
            contract = get_contract(vt_symbol)
        except Exception:
            return ""
        return str(getattr(contract, "name", "") or "").strip() if contract is not None else ""

    def _name_from_database(self, vt_symbol: str) -> str:
        peewee_database = getattr(self.database, "db", None)
        if peewee_database is None:
            return ""
        placeholder = getattr(peewee_database, "param", "?")
        try:
            cursor = peewee_database.execute_sql(
                "SELECT name, short_name FROM security_entity "
                f"WHERE vt_symbol = {placeholder} LIMIT 1",
                (vt_symbol,),
            )
            row = cursor.fetchone()
        except Exception:
            return ""
        if not row:
            return ""
        if isinstance(row, dict):
            return str(row.get("short_name") or row.get("name") or "").strip()
        if isinstance(row, (list, tuple)):
            return str((row[1] if len(row) > 1 else "") or row[0] or "").strip()
        return str(getattr(row, "short_name", "") or getattr(row, "name", "") or "").strip()
