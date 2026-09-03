from datetime import date
import unittest
from unittest.mock import Mock

from quantrade_research.alpaca import AlpacaError, AlpacaMarketDataProvider
from quantrade_research.ingest_benchmark_data import _source_inputs_for_artifacts
from quantrade_research.market_provider import (
    MarketDataProvider, MarketProviderMetadata, ProviderPage, validate_provider,
)
from quantrade_research.market_provider_registry import available_market_providers, create_market_data_provider


METADATA = MarketProviderMetadata(
    provider_id="alternate",
    bars_source_reference="https://alternate.example/bars",
    actions_source_reference="https://alternate.example/actions",
    bars_response_category="alternate_bars",
    actions_response_category="alternate_actions",
    bars_parser_version="alternate_bars_v1",
    actions_parser_version="alternate_actions_v1",
    equity_bar_availability_rule=("alternate_retrieval", "v1"),
    benchmark_bar_availability_rule=("alternate_retrieval", "v1-benchmark"),
    benchmark_action_availability_rule=("alternate_retrieval", "v1-actions"),
)


class AlternateProvider:
    metadata = METADATA

    def fetch_daily_bars(self, symbols, start, end, adjustment_basis, page_token=None):
        return ProviderPage((), b'{"bars":{}}', None)

    def fetch_corporate_actions(self, symbols, start, end, page_token=None):
        return ProviderPage((), b'{"corporate_actions":{}}', None)


class MarketProviderTests(unittest.TestCase):
    def test_alternate_adapter_satisfies_provider_contract(self) -> None:
        provider = AlternateProvider()
        self.assertIsInstance(provider, MarketDataProvider)
        validate_provider(provider)
        page = provider.fetch_daily_bars(["AAPL"], date(2026, 9, 1), date(2026, 9, 1), "split_adjusted")
        self.assertEqual(page.records, ())
        self.assertEqual(page.raw_payload, b'{"bars":{}}')

    def test_manifest_lineage_comes_from_selected_provider(self) -> None:
        sources = _source_inputs_for_artifacts(
            ["receipt://alternate/bars/hash"], ["receipt://alternate/actions/hash"], METADATA,
        )
        self.assertEqual([source.provider for source in sources], ["alternate", "alternate"])
        self.assertEqual(sources[0].source_reference, METADATA.bars_source_reference)
        self.assertEqual(sources[1].source_reference, METADATA.actions_source_reference)

    def test_alpaca_adapter_maps_canonical_adjustments_and_preserves_payload(self) -> None:
        provider = object.__new__(AlpacaMarketDataProvider)
        provider._client = Mock()
        payload = b'{"bars":{},"next_page_token":"next"}'
        provider._client.fetch_daily_bars.return_value = payload
        page = provider.fetch_daily_bars(
            ["AAPL"], date(2026, 9, 1), date(2026, 9, 2), "split_adjusted",
        )
        provider._client.fetch_daily_bars.assert_called_once_with(
            ["AAPL"], date(2026, 9, 1), date(2026, 9, 2), "split", None,
        )
        self.assertEqual(page.raw_payload, payload)
        self.assertEqual(page.next_page_token, "next")
        with self.assertRaisesRegex(AlpacaError, "unsupported canonical"):
            provider.fetch_daily_bars(
                ["AAPL"], date(2026, 9, 1), date(2026, 9, 2), "mystery",
            )

    def test_registry_is_explicit_and_rejects_unknown_provider(self) -> None:
        self.assertEqual(available_market_providers(), ("alpaca",))
        with self.assertRaisesRegex(ValueError, "unknown market-data provider"):
            create_market_data_provider("unknown", Mock())

    def test_metadata_rejects_unsafe_source_references(self) -> None:
        values = {name: getattr(METADATA, name) for name in METADATA.__dataclass_fields__}
        values["bars_source_reference"] = "http://alternate.example/bars"
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            MarketProviderMetadata(**values)


if __name__ == "__main__":
    unittest.main()
