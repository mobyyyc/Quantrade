"""Explicit provider registry; selection never changes normalized ingestion."""

from __future__ import annotations

from collections.abc import Callable

from .config import Settings
from .market_provider import MarketDataProvider, validate_provider


ProviderFactory = Callable[[Settings], MarketDataProvider]


def _alpaca(settings: Settings) -> MarketDataProvider:
    from .alpaca import AlpacaMarketDataProvider
    settings.require_alpaca_access()
    assert settings.alpaca_key_id and settings.alpaca_secret_key
    return AlpacaMarketDataProvider(settings.alpaca_key_id, settings.alpaca_secret_key)


_PROVIDERS: dict[str, ProviderFactory] = {"alpaca": _alpaca}


def available_market_providers() -> tuple[str, ...]:
    return tuple(sorted(_PROVIDERS))


def create_market_data_provider(name: str, settings: Settings) -> MarketDataProvider:
    try:
        factory = _PROVIDERS[name.lower()]
    except KeyError as error:
        choices = ", ".join(available_market_providers())
        raise ValueError(f"unknown market-data provider {name!r}; available: {choices}") from error
    provider = factory(settings)
    validate_provider(provider)
    return provider
