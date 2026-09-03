"""Provider-neutral market-data contracts used by normalized ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Generic, Protocol, TypeVar, runtime_checkable


ADJUSTMENT_BASES = ("unadjusted", "split_adjusted", "total_return_adjusted")


@dataclass(frozen=True, slots=True)
class DailyBar:
    ticker: str
    session_date: date
    observed_at: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal


@dataclass(frozen=True, slots=True)
class CorporateAction:
    provider_action_id: str
    ticker: str
    action_type: str
    process_date: date
    effective_date: date | None
    cash_amount: Decimal | None
    ratio_numerator: Decimal | None
    ratio_denominator: Decimal | None
    payload: dict[str, Any]


Record = TypeVar("Record")


@dataclass(frozen=True, slots=True)
class ProviderPage(Generic[Record]):
    """Canonical records accompanied by the exact response used to parse them."""

    records: tuple[Record, ...]
    raw_payload: bytes
    next_page_token: str | None


@dataclass(frozen=True, slots=True)
class MarketProviderMetadata:
    provider_id: str
    bars_source_reference: str
    actions_source_reference: str
    bars_response_category: str
    actions_response_category: str
    bars_parser_version: str
    actions_parser_version: str
    equity_bar_availability_rule: tuple[str, str]
    benchmark_bar_availability_rule: tuple[str, str]
    benchmark_action_availability_rule: tuple[str, str]

    def __post_init__(self) -> None:
        if not self.provider_id or self.provider_id != self.provider_id.lower():
            raise ValueError("provider_id must be a non-empty lowercase identifier")
        if not self.bars_source_reference.startswith("https://"):
            raise ValueError("bar source reference must use HTTPS")
        if not self.actions_source_reference.startswith("https://"):
            raise ValueError("corporate-action source reference must use HTTPS")


@runtime_checkable
class MarketDataProvider(Protocol):
    """Adapter boundary required by routine normalized market ingestion.

    Implementations own authentication, symbol translation, pagination, wire
    parsing, and provider-specific adjustment names. Consumers see only the
    canonical records above and preserve the returned raw payload as lineage.
    """

    @property
    def metadata(self) -> MarketProviderMetadata: ...

    def fetch_daily_bars(
        self, symbols: list[str], start: date, end: date, adjustment_basis: str,
        page_token: str | None = None,
    ) -> ProviderPage[DailyBar]: ...

    def fetch_corporate_actions(
        self, symbols: list[str], start: date, end: date,
        page_token: str | None = None,
    ) -> ProviderPage[CorporateAction]: ...


def validate_provider(provider: MarketDataProvider) -> None:
    """Fail before retrieval when an adapter does not satisfy the contract."""
    if not isinstance(provider, MarketDataProvider):
        raise TypeError("market-data provider does not implement the required contract")
    metadata = provider.metadata
    required_rules = (
        metadata.equity_bar_availability_rule,
        metadata.benchmark_bar_availability_rule,
        metadata.benchmark_action_availability_rule,
    )
    if any(len(rule) != 2 or not all(rule) for rule in required_rules):
        raise ValueError("provider availability rules require non-empty key and version")
