"""Alpaca market-data adapter with explicit adjustment and availability metadata."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import json
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .market_provider import (
    CorporateAction as AlpacaCorporateAction,
    DailyBar as AlpacaDailyBar,
    MarketProviderMetadata,
    ProviderPage,
)


ALPACA_BARS_URL = "https://data.alpaca.markets/v2/stocks/bars"
ALPACA_CORPORATE_ACTIONS_URL = "https://data.alpaca.markets/v1/corporate-actions"


class AlpacaError(ValueError):
    pass


def _alpaca_symbol(ticker: str) -> str:
    """Translate the security-master share-class separator to Alpaca's notation."""
    return ticker.upper().replace("-", ".")


def _security_master_ticker(ticker: str) -> str:
    """Translate Alpaca's share-class separator back to the master notation."""
    return ticker.upper().replace(".", "-")


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise AlpacaError("bar timestamp is missing")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _decimal(value: object, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as error:
        raise AlpacaError(f"invalid Alpaca {field}") from error


def parse_daily_bars(payload: bytes) -> tuple[list[AlpacaDailyBar], str | None]:
    try:
        document = json.loads(payload)
        bars_by_symbol = document["bars"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise AlpacaError("Alpaca bars response has an invalid shape") from error
    if not isinstance(bars_by_symbol, dict):
        raise AlpacaError("Alpaca bars payload is not grouped by symbol")
    bars: list[AlpacaDailyBar] = []
    for ticker, values in bars_by_symbol.items():
        if not isinstance(ticker, str) or not isinstance(values, list):
            raise AlpacaError("Alpaca bars payload contains an invalid symbol group")
        for value in values:
            if not isinstance(value, dict):
                raise AlpacaError("Alpaca bars payload contains an invalid bar")
            timestamp = _parse_timestamp(value.get("t"))
            bars.append(
                AlpacaDailyBar(
                    ticker=_security_master_ticker(ticker), session_date=timestamp.date(), observed_at=timestamp,
                    open_price=_decimal(value.get("o"), "open"), high_price=_decimal(value.get("h"), "high"),
                    low_price=_decimal(value.get("l"), "low"), close_price=_decimal(value.get("c"), "close"),
                    volume=_decimal(value.get("v"), "volume"),
                )
            )
    token = document.get("next_page_token")
    if token is not None and not isinstance(token, str):
        raise AlpacaError("Alpaca next_page_token is invalid")
    return bars, token


def parse_corporate_actions(payload: bytes) -> tuple[list[AlpacaCorporateAction], str | None]:
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as error:
        raise AlpacaError("Alpaca corporate-actions response is not JSON") from error
    if not isinstance(document, dict):
        raise AlpacaError("Alpaca corporate-actions response has an invalid shape")
    action_groups = document.get("corporate_actions", document)
    if not isinstance(action_groups, dict):
        raise AlpacaError("Alpaca corporate-actions response has invalid action groups")
    actions: list[AlpacaCorporateAction] = []
    for action_type, values in action_groups.items():
        if action_type == "next_page_token":
            continue
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, dict):
                raise AlpacaError("Alpaca corporate-actions response contains an invalid action")
            symbol = (
                value.get("symbol")
                or value.get("acquirer_symbol")
                or value.get("acquiree_symbol")
                or value.get("new_symbol")
                or value.get("old_symbol")
            )
            if not symbol:
                # Preserve the raw provider response but do not invent an
                # identity for an action without a tradable security mapping.
                continue
            try:
                action_id = str(value["id"])
                ticker = _security_master_ticker(str(symbol))
                process_date = date.fromisoformat(str(value["process_date"]))
            except (KeyError, ValueError) as error:
                raise AlpacaError("corporate action is missing id, symbol, or process_date") from error
            effective = value.get("ex_date") or value.get("effective_date")
            ratio = value.get("ratio") if isinstance(value.get("ratio"), dict) else {}
            actions.append(
                AlpacaCorporateAction(
                    provider_action_id=action_id, ticker=ticker, action_type=action_type.rstrip("s"),
                    process_date=process_date,
                    effective_date=date.fromisoformat(str(effective)) if effective else None,
                    cash_amount=_decimal(value.get("cash", value.get("rate")), "cash") if value.get("cash", value.get("rate")) is not None else None,
                    ratio_numerator=_decimal(ratio["numerator"], "ratio numerator") if ratio.get("numerator") is not None else None,
                    ratio_denominator=_decimal(ratio["denominator"], "ratio denominator") if ratio.get("denominator") is not None else None,
                    payload=value,
                )
            )
    token = document.get("next_page_token")
    if token is not None and not isinstance(token, str):
        raise AlpacaError("Alpaca next_page_token is invalid")
    return actions, token


class AlpacaClient:
    def __init__(self, key_id: str, secret_key: str, timeout_seconds: float = 30.0) -> None:
        if not key_id or not secret_key:
            raise AlpacaError("Alpaca credentials are required")
        self._headers = {"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret_key, "Accept": "application/json"}
        self._timeout_seconds = timeout_seconds

    def _fetch(self, url: str, parameters: dict[str, str]) -> bytes:
        request = Request(f"{url}?{urlencode(parameters)}", headers=self._headers)
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                if response.status != 200:
                    raise AlpacaError(f"Alpaca returned HTTP {response.status}")
                return response.read()
        except HTTPError as error:
            detail = error.read().decode("utf-8", "replace").strip()
            raise AlpacaError(f"Alpaca returned HTTP {error.code}: {detail[:500]}") from error

    def fetch_daily_bars(self, symbols: list[str], start: date, end: date, adjustment: str, page_token: str | None = None) -> bytes:
        parameters = {"symbols": ",".join(_alpaca_symbol(symbol) for symbol in symbols), "timeframe": "1Day", "start": start.isoformat(), "end": end.isoformat(), "adjustment": adjustment, "feed": "iex"}
        if page_token:
            parameters["page_token"] = page_token
        return self._fetch(ALPACA_BARS_URL, parameters)

    def fetch_corporate_actions(self, symbols: list[str], start: date, end: date, page_token: str | None = None) -> bytes:
        parameters = {"symbols": ",".join(_alpaca_symbol(symbol) for symbol in symbols), "start": start.isoformat(), "end": end.isoformat(), "region": "us", "data_quality": "complete"}
        if page_token:
            parameters["page_token"] = page_token
        return self._fetch(ALPACA_CORPORATE_ACTIONS_URL, parameters)


ALPACA_PROVIDER_METADATA = MarketProviderMetadata(
    provider_id="alpaca",
    bars_source_reference=ALPACA_BARS_URL,
    actions_source_reference=ALPACA_CORPORATE_ACTIONS_URL,
    bars_response_category="alpaca_daily_bars",
    actions_response_category="alpaca_corporate_actions",
    bars_parser_version="alpaca_parser_v1",
    actions_parser_version="alpaca_corporate_actions_v1",
    equity_bar_availability_rule=("alpaca_retrieval", "v1"),
    benchmark_bar_availability_rule=("alpaca_retrieval", "v1-benchmark"),
    benchmark_action_availability_rule=("alpaca_retrieval", "v1-benchmark-corporate-action"),
)


class AlpacaMarketDataProvider:
    """Translate Alpaca transport and wire formats into canonical records."""

    metadata = ALPACA_PROVIDER_METADATA
    _adjustments = {
        "unadjusted": "raw",
        "split_adjusted": "split",
        "total_return_adjusted": "all",
    }

    def __init__(self, key_id: str, secret_key: str, timeout_seconds: float = 30.0) -> None:
        self._client = AlpacaClient(key_id, secret_key, timeout_seconds)

    def fetch_daily_bars(
        self, symbols: list[str], start: date, end: date, adjustment_basis: str,
        page_token: str | None = None,
    ) -> ProviderPage[AlpacaDailyBar]:
        try:
            adjustment = self._adjustments[adjustment_basis]
        except KeyError as error:
            raise AlpacaError(f"unsupported canonical adjustment basis: {adjustment_basis}") from error
        payload = self._client.fetch_daily_bars(symbols, start, end, adjustment, page_token)
        records, token = parse_daily_bars(payload)
        return ProviderPage(tuple(records), payload, token)

    def fetch_corporate_actions(
        self, symbols: list[str], start: date, end: date,
        page_token: str | None = None,
    ) -> ProviderPage[AlpacaCorporateAction]:
        payload = self._client.fetch_corporate_actions(symbols, start, end, page_token)
        records, token = parse_corporate_actions(payload)
        return ProviderPage(tuple(records), payload, token)
