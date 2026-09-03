"""Tests for compact provenance retained by routine market-data ingestion."""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

from quantrade_research.ingest_benchmark_data import _should_fetch_adjustment, _source_inputs_for_artifacts
from quantrade_research.alpaca import ALPACA_PROVIDER_METADATA
from quantrade_research.ingest_market_data import _symbols_to_fetch
from quantrade_research.market_data import CompactMarketReceipt, record_market_source
from quantrade_research.security_master import RawArtifact


class MarketReceiptTests(unittest.TestCase):
    def test_retained_payload_provenance_uses_selected_provider(self) -> None:
        retrieved_at = datetime(2026, 8, 27, tzinfo=timezone.utc)
        artifact = RawArtifact("file:///raw/alternate.json", "a" * 64, retrieved_at)

        class Repository:
            def persist_raw_artifact(self, stored, source_reference, *, provider):
                self.request = (stored, source_reference, provider)
                return "artifact-id"

        class FileStore:
            def store(self, payload, observed_at, *, category):
                self.request = (payload, observed_at, category)
                return artifact

        repository, store = Repository(), FileStore()
        source = record_market_source(
            repository, store, b"payload", retrieved_at, "https://alternate.example/bars",
            response_category="alternate_bars", raw_category="alternate-market-data",
            compact_receipts=False, parser_version="alternate_v1", provider="alternate",
        )
        self.assertEqual(repository.request[2], "alternate")
        self.assertEqual(store.request[2], "alternate-market-data")
        self.assertEqual(source.storage_uri, artifact.storage_uri)

    def test_compact_market_receipt_never_writes_a_payload_file(self) -> None:
        expected = CompactMarketReceipt(
            "artifact-id", "receipt://alpaca/reference/hash", "receipt-id",
        )

        class Repository:
            def persist_compact_receipt(self, payload, source_reference, response_category, retrieved_at, *, parser_version, provider):
                self.request = (payload, source_reference, response_category, retrieved_at, parser_version, provider)
                return expected

        class FileStore:
            def store(self, *args, **kwargs):
                raise AssertionError("compact receipt mode must not write a payload file")

        repository = Repository()
        result = record_market_source(
            repository, FileStore(), b'{"bars":{}}', datetime(2026, 8, 27, tzinfo=timezone.utc),
            "https://data.alpaca.markets/v2/stocks/bars", response_category="alpaca_daily_bars",
            raw_category="market-data", compact_receipts=True, parser_version="alpaca_parser_v1",
            provider="alpaca",
        )

        self.assertEqual(result.raw_artifact_id, "artifact-id")
        self.assertEqual(result.storage_uri, "receipt://alpaca/reference/hash")
        self.assertEqual(result.source_receipt_id, "receipt-id")
        self.assertEqual(repository.request[2], "alpaca_daily_bars")
        self.assertEqual(repository.request[4], "alpaca_parser_v1")
        self.assertEqual(repository.request[5], "alpaca")

    def test_missing_only_stock_plan_skips_symbols_with_complete_bars(self) -> None:
        class Repository:
            def symbols_missing_daily_bars(self, symbols, start, end, adjustment_basis):
                self.request = (symbols, start, end, adjustment_basis)
                return ["AAPL"]

        repository = Repository()
        result = _symbols_to_fetch(
            repository, ["AAPL", "MSFT"], date(2026, 8, 27), date(2026, 8, 27),
            "split_adjusted", only_missing=True,
        )
        self.assertEqual(result, ["AAPL"])
        self.assertEqual(repository.request[3], "split_adjusted")

    def test_missing_only_benchmark_plan_skips_an_existing_adjustment(self) -> None:
        class Repository:
            def benchmark_bar_exists(self, ticker, session_date, adjustment_basis):
                self.request = (ticker, session_date, adjustment_basis)
                return True

        repository = Repository()
        self.assertFalse(_should_fetch_adjustment(
            repository, "SPY", date(2026, 8, 27), "split_adjusted", only_missing=True,
        ))
        self.assertTrue(_should_fetch_adjustment(
            repository, "SPY", date(2026, 8, 27), "split_adjusted", only_missing=False,
        ))

    def test_benchmark_retry_with_no_downloads_has_no_ingestion_lineage(self) -> None:
        self.assertEqual(_source_inputs_for_artifacts([], [], ALPACA_PROVIDER_METADATA), ())

        source_inputs = _source_inputs_for_artifacts(
            ["receipt://alpaca/bars/hash"], [], ALPACA_PROVIDER_METADATA,
        )
        self.assertEqual(len(source_inputs), 1)
        self.assertEqual(source_inputs[0].raw_artifact_uris, ("receipt://alpaca/bars/hash",))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
