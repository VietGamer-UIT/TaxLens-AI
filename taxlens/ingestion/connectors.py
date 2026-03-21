"""ERP connectors — interface-ready mocks for SAP, Oracle, MISA."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ERPConnector(ABC):
    name: str

    @abstractmethod
    def fetch_general_ledger(self, period: str) -> list[dict[str, Any]]:
        """Return GL rows for accounting period (YYYY-MM)."""

    @abstractmethod
    def healthcheck(self) -> bool:
        """Return True if credentials and endpoint are valid."""


class SAPConnector(ERPConnector):
    name = "SAP"

    def __init__(self, base_url: str, client: str) -> None:
        self._base_url = base_url
        self._client = client

    def fetch_general_ledger(self, period: str) -> list[dict[str, Any]]:
        _ = period
        return []

    def healthcheck(self) -> bool:
        return bool(self._base_url)


class OracleConnector(ERPConnector):
    name = "Oracle"

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def fetch_general_ledger(self, period: str) -> list[dict[str, Any]]:
        _ = period
        return []

    def healthcheck(self) -> bool:
        return bool(self._dsn)


class MISAConnector(ERPConnector):
    name = "MISA"

    def __init__(self, api_base: str) -> None:
        self._api_base = api_base

    def fetch_general_ledger(self, period: str) -> list[dict[str, Any]]:
        _ = period
        return []

    def healthcheck(self) -> bool:
        return bool(self._api_base)
