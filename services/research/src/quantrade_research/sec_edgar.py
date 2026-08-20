"""Minimal, rate-conscious client for SEC EDGAR reference data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from typing import Any
from urllib.request import Request, urlopen


COMPANY_TICKERS_EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"

EXCHANGE_MIC_BY_SEC_NAME = {
    "Nasdaq": "XNAS",
    "NYSE": "XNYS",
    "NYSE American": "XASE",
    "NYSE Arca": "ARCX",
    "Cboe BZX": "BATS",
}


class SecEdgarError(ValueError):
    """Raised when SEC reference data is unavailable or malformed."""


@dataclass(frozen=True, slots=True)
class SecTickerAssociation:
    cik: str
    name: str
    ticker: str
    exchange: str


@dataclass(frozen=True, slots=True)
class SecurityMasterRow:
    cik: str
    issuer_name: str
    ticker: str
    exchange_mic: str
    snapshot_date: date


def parse_company_tickers_exchange(payload: bytes) -> list[SecTickerAssociation]:
    try:
        document: dict[str, Any] = json.loads(payload)
        fields = document["fields"]
        data = document["data"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise SecEdgarError("SEC ticker/exchange payload has an invalid shape") from error

    if fields != ["cik", "name", "ticker", "exchange"] or not isinstance(data, list):
        raise SecEdgarError("SEC ticker/exchange payload fields changed unexpectedly")

    associations: list[SecTickerAssociation] = []
    for row in data:
        if not isinstance(row, list) or len(row) != 4:
            raise SecEdgarError("SEC ticker/exchange payload contains an invalid row")
        cik, name, ticker, exchange = row
        if not all(isinstance(value, (str, int)) for value in row):
            raise SecEdgarError("SEC ticker/exchange payload contains a non-scalar value")
        cik_text = str(cik).zfill(10)
        if not cik_text.isdigit() or not str(name).strip() or not str(ticker).strip():
            raise SecEdgarError("SEC ticker/exchange payload contains an invalid association")
        associations.append(
            SecTickerAssociation(cik_text, str(name).strip(), str(ticker).strip(), str(exchange).strip())
        )
    return associations


def normalize_security_master(
    associations: list[SecTickerAssociation], snapshot_date: date
) -> tuple[list[SecurityMasterRow], list[SecTickerAssociation]]:
    rows: list[SecurityMasterRow] = []
    unmapped: list[SecTickerAssociation] = []
    for association in associations:
        exchange_mic = EXCHANGE_MIC_BY_SEC_NAME.get(association.exchange)
        if exchange_mic is None:
            unmapped.append(association)
            continue
        rows.append(
            SecurityMasterRow(
                cik=association.cik,
                issuer_name=association.name,
                ticker=association.ticker.upper(),
                exchange_mic=exchange_mic,
                snapshot_date=snapshot_date,
            )
        )
    return rows, unmapped


class SecEdgarClient:
    def __init__(self, user_agent: str, timeout_seconds: float = 30.0) -> None:
        if not user_agent.strip():
            raise SecEdgarError("a descriptive SEC user agent is required")
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds

    def fetch_company_tickers_exchange(self) -> bytes:
        request = Request(
            COMPANY_TICKERS_EXCHANGE_URL,
            headers={"Accept": "application/json", "User-Agent": self._user_agent},
        )
        with urlopen(request, timeout=self._timeout_seconds) as response:
            if response.status != 200:
                raise SecEdgarError(f"SEC returned HTTP {response.status}")
            return response.read()
