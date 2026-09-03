"""Provider-neutral PostgreSQL persistence for normalized market data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Callable

from .market_provider import CorporateAction, DailyBar
from .security_master import FileRawArtifactStore, RawArtifact


@dataclass(frozen=True, slots=True)
class CompactMarketReceipt:
    raw_artifact_id: str
    storage_uri: str
    source_receipt_id: str


@dataclass(frozen=True, slots=True)
class MarketSource:
    """Immutable source reference used by normalized market-data rows."""

    raw_artifact_id: str
    storage_uri: str
    source_receipt_id: str | None = None


class PostgresMarketDataRepository:
    def __init__(self, database_url: str) -> None:
        try:
            import psycopg
        except ImportError as error:  # pragma: no cover
            raise RuntimeError("Install quantrade-research dependencies before database ingestion") from error
        self._connection = psycopg.connect(database_url)

    def close(self) -> None:
        self._connection.close()

    def persist_raw_artifact(self, artifact: RawArtifact, source_reference: str, *, provider: str) -> str:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO quantrade.raw_artifacts
                    (provider, source_reference, storage_uri, retrieved_at, content_sha256)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (storage_uri) DO UPDATE SET storage_uri = EXCLUDED.storage_uri
                RETURNING raw_artifact_id, provider
                """,
                (provider, source_reference, artifact.storage_uri, artifact.retrieved_at, artifact.content_sha256),
            )
            row = cursor.fetchone()
            if row[1] != provider:
                raise ValueError("raw artifact storage URI is already owned by another provider")
            identifier = str(row[0])
            cursor.execute(
                """INSERT INTO quantrade.raw_documents (provider, content_sha256, canonical_storage_uri)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (provider, content_sha256) DO NOTHING""",
                (provider, artifact.content_sha256, artifact.storage_uri),
            )
            cursor.execute(
                """SELECT raw_document_id FROM quantrade.raw_documents
                   WHERE provider = %s AND content_sha256 = %s""",
                (provider, artifact.content_sha256),
            )
            document_id = cursor.fetchone()[0]
            cursor.execute(
                """INSERT INTO quantrade.raw_document_retrievals
                       (raw_document_id, raw_artifact_id, source_reference, retrieved_at)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (raw_artifact_id) DO NOTHING""",
                (document_id, identifier, source_reference, artifact.retrieved_at),
            )
        self._connection.commit()
        return identifier

    def persist_compact_receipt(
        self, payload: bytes, source_reference: str, response_category: str,
        retrieved_at: datetime, *, parser_version: str, provider: str,
    ) -> CompactMarketReceipt:
        """Persist market-source metadata without retaining the response payload."""
        content_sha256 = sha256(payload).hexdigest()
        source_key = sha256(source_reference.encode("utf-8")).hexdigest()
        storage_uri = f"receipt://{provider}/{source_key}/{content_sha256}"
        with self._connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO quantrade.raw_artifacts
                       (provider, source_reference, storage_uri, retrieved_at, content_sha256)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (storage_uri) DO UPDATE SET storage_uri = EXCLUDED.storage_uri
                   RETURNING raw_artifact_id""",
                (provider, source_reference, storage_uri, retrieved_at, content_sha256),
            )
            raw_artifact_id = str(cursor.fetchone()[0])
            cursor.execute(
                """INSERT INTO quantrade.source_receipts
                       (provider, source_reference, response_category, content_sha256, byte_count, parser_version,
                        payload_retained, content_type)
                   VALUES (%s, %s, %s, %s, %s, %s, FALSE, 'application/json')
                   ON CONFLICT (provider, source_reference, content_sha256, parser_version) DO NOTHING
                   RETURNING source_receipt_id""",
                (provider, source_reference, response_category, content_sha256, len(payload), parser_version),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    """SELECT source_receipt_id FROM quantrade.source_receipts
                       WHERE provider = %s AND source_reference = %s
                         AND content_sha256 = %s AND parser_version = %s""",
                    (provider, source_reference, content_sha256, parser_version),
                )
                row = cursor.fetchone()
            source_receipt_id = str(row[0])
            cursor.execute(
                """INSERT INTO quantrade.source_receipt_retrievals
                       (source_receipt_id, retrieved_at, retrieval_context)
                   VALUES (%s, %s, jsonb_build_object('retention_mode', 'metadata_only'))
                   ON CONFLICT (source_receipt_id, retrieved_at) DO NOTHING""",
                (source_receipt_id, retrieved_at),
            )
        self._connection.commit()
        return CompactMarketReceipt(raw_artifact_id, storage_uri, source_receipt_id)

    def availability_rule_id(self, rule_key: str, rule_version: str, data_domain: str) -> str:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT availability_rule_id::text FROM quantrade.availability_rules
                   WHERE rule_key = %s AND rule_version = %s AND data_domain = %s""",
                (rule_key, rule_version, data_domain),
            )
            row = cursor.fetchone()
        if row is None:
            raise ValueError(f"availability rule {rule_key}@{rule_version} is unavailable for {data_domain}")
        return str(row[0])

    def symbols_missing_daily_bars(
        self, tickers: list[str], start_date, end_date, adjustment_basis: str,
    ) -> list[str]:
        """Return requested active listings without a bar for every known SPY session.

        SPY is the trading-session authority for the research system. The daily
        runner ingests it first, so this query makes stock requests strictly
        additive while preserving any already recorded observation.
        """
        if not tickers:
            return []
        with self._connection.cursor() as cursor:
            cursor.execute(
                """WITH requested(ticker) AS (SELECT unnest(%s::text[])),
                         sessions AS (
                           SELECT session_date FROM quantrade.benchmark_daily_price_bars
                           WHERE benchmark_ticker = 'SPY' AND session = 'regular'
                             AND adjustment_basis = 'split_adjusted'
                             AND session_date BETWEEN %s AND %s
                         )
                   SELECT requested.ticker
                   FROM requested
                   JOIN quantrade.listings listing
                     ON listing.ticker = requested.ticker AND listing.valid_to IS NULL
                   WHERE EXISTS (
                     SELECT 1 FROM sessions
                   )
                     AND EXISTS (
                       SELECT 1 FROM sessions
                       LEFT JOIN quantrade.daily_price_bars bar
                         ON bar.security_id = listing.security_id
                        AND bar.session_date = sessions.session_date
                        AND bar.session = 'regular'
                        AND bar.adjustment_basis = %s
                       WHERE bar.security_id IS NULL
                     )
                   ORDER BY requested.ticker""",
                (tickers, start_date, end_date, adjustment_basis),
            )
            return [str(row[0]) for row in cursor.fetchall()]

    def benchmark_bar_exists(self, ticker: str, session_date, adjustment_basis: str) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT EXISTS (
                       SELECT 1 FROM quantrade.benchmark_daily_price_bars
                       WHERE benchmark_ticker = %s AND session_date = %s AND session = 'regular'
                         AND adjustment_basis = %s
                   )""",
                (ticker, session_date, adjustment_basis),
            )
            return bool(cursor.fetchone()[0])

    def _security_id(self, cursor, ticker: str, on_date) -> object:
        cursor.execute(
            """
            SELECT security_id FROM quantrade.listings
            WHERE ticker = %s AND valid_from <= %s AND (valid_to IS NULL OR valid_to > %s)
            ORDER BY valid_from DESC LIMIT 1
            """,
            (ticker, on_date, on_date),
        )
        row = cursor.fetchone()
        if row is None:
            # The Tier-B master represents the current universe, so its validity
            # start is the ingestion date rather than the listing's historical
            # start. Allow a current active listing to receive a historical
            # backfill while retaining the dated lookup as the primary path.
            cursor.execute(
                """
                SELECT security_id FROM quantrade.listings
                WHERE ticker = %s AND valid_to IS NULL
                ORDER BY valid_from DESC LIMIT 1
                """,
                (ticker,),
            )
            row = cursor.fetchone()
        if row is None:
            raise ValueError(f"no active security-master listing for {ticker} on {on_date}")
        return row[0]

    def upsert_daily_bars(
        self, bars: list[DailyBar], adjustment_basis: str, raw_artifact_id: str,
        source_reference: str, available_at: datetime | Callable[[DailyBar], datetime],
        availability_rule_id: str, *, source_receipt_id: str | None = None,
        skip_existing: bool = False,
    ) -> int:
        persisted = 0
        conflict_clause = """DO NOTHING""" if skip_existing else """DO UPDATE SET
            open_price = EXCLUDED.open_price, high_price = EXCLUDED.high_price,
            low_price = EXCLUDED.low_price, close_price = EXCLUDED.close_price,
            volume = EXCLUDED.volume, observed_at = EXCLUDED.observed_at,
            available_at = EXCLUDED.available_at, availability_rule_id = EXCLUDED.availability_rule_id,
            ingested_at = EXCLUDED.ingested_at,
            raw_artifact_id = EXCLUDED.raw_artifact_id, source_reference = EXCLUDED.source_reference,
            source_receipt_id = COALESCE(EXCLUDED.source_receipt_id, quantrade.daily_price_bars.source_receipt_id)"""
        with self._connection.cursor() as cursor:
            for bar in bars:
                security_id = self._security_id(cursor, bar.ticker, bar.session_date)
                bar_available_at = available_at(bar) if callable(available_at) else available_at
                cursor.execute(
                    f"""
                    INSERT INTO quantrade.daily_price_bars
                        (security_id, session_date, session, currency, open_price, high_price, low_price,
                         close_price, volume, adjustment_basis, observed_at, available_at, availability_rule_id, ingested_at,
                         raw_artifact_id, source_reference, source_receipt_id)
                    VALUES (%s, %s, 'regular', 'USD', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (security_id, session_date, session, adjustment_basis)
                    {conflict_clause}""",
                    (security_id, bar.session_date, bar.open_price, bar.high_price, bar.low_price,
                     bar.close_price, bar.volume, adjustment_basis, bar.observed_at, bar_available_at,
                     availability_rule_id, datetime.now(timezone.utc), raw_artifact_id, source_reference, source_receipt_id),
                )
                persisted += cursor.rowcount
        self._connection.commit()
        return persisted

    def upsert_benchmark_daily_bars(
        self, bars: list[DailyBar], benchmark_ticker: str, adjustment_basis: str,
        raw_artifact_id: str, source_reference: str,
        available_at: datetime | Callable[[DailyBar], datetime], availability_rule_id: str,
        *, source_receipt_id: str | None = None, skip_existing: bool = False,
    ) -> int:
        persisted = 0
        conflict_clause = "DO NOTHING" if skip_existing else """DO UPDATE SET
            open_price = EXCLUDED.open_price, high_price = EXCLUDED.high_price,
            low_price = EXCLUDED.low_price, close_price = EXCLUDED.close_price,
            volume = EXCLUDED.volume, observed_at = EXCLUDED.observed_at,
            available_at = EXCLUDED.available_at,
            availability_rule_id = EXCLUDED.availability_rule_id,
            ingested_at = EXCLUDED.ingested_at,
            raw_artifact_id = EXCLUDED.raw_artifact_id,
            source_reference = EXCLUDED.source_reference,
            source_receipt_id = COALESCE(EXCLUDED.source_receipt_id, quantrade.benchmark_daily_price_bars.source_receipt_id)"""
        with self._connection.cursor() as cursor:
            for bar in bars:
                bar_available_at = available_at(bar) if callable(available_at) else available_at
                cursor.execute(
                    f"""INSERT INTO quantrade.benchmark_daily_price_bars
                           (benchmark_ticker, session_date, session, currency, open_price, high_price, low_price,
                            close_price, volume, adjustment_basis, observed_at, available_at, availability_rule_id,
                            ingested_at, raw_artifact_id, source_reference, source_receipt_id)
                       VALUES (%s, %s, 'regular', 'USD', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (benchmark_ticker, session_date, session, adjustment_basis)
                       {conflict_clause}""",
                    (benchmark_ticker, bar.session_date, bar.open_price, bar.high_price, bar.low_price,
                     bar.close_price, bar.volume, adjustment_basis, bar.observed_at, bar_available_at,
                     availability_rule_id, datetime.now(timezone.utc), raw_artifact_id, source_reference, source_receipt_id),
                )
                persisted += cursor.rowcount
        self._connection.commit()
        return persisted

    def upsert_corporate_actions(
        self, actions: list[CorporateAction], raw_artifact_id: str, source_reference: str,
        available_at: datetime | Callable[[CorporateAction], datetime], *,
        skip_unmapped: bool = False, source_receipt_id: str | None = None,
        retain_provider_payload: bool = True,
    ) -> int:
        persisted = 0
        with self._connection.cursor() as cursor:
            for action in actions:
                try:
                    security_id = self._security_id(cursor, action.ticker, action.effective_date or action.process_date)
                except ValueError:
                    if skip_unmapped:
                        continue
                    raise
                action_available_at = available_at(action) if callable(available_at) else available_at
                cursor.execute(
                    """
                    INSERT INTO quantrade.corporate_actions
                        (security_id, provider_action_id, action_type, process_date, effective_date,
                         cash_amount, ratio_numerator, ratio_denominator, currency, available_at,
                         ingested_at, raw_artifact_id, source_reference, provider_payload, source_receipt_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'USD', %s, %s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (provider_action_id) DO NOTHING
                    """,
                    (security_id, action.provider_action_id, action.action_type, action.process_date,
                     action.effective_date, action.cash_amount, action.ratio_numerator,
                     action.ratio_denominator, action_available_at, datetime.now(timezone.utc), raw_artifact_id,
                     source_reference, json.dumps(action.payload, sort_keys=True) if retain_provider_payload else "{}",
                     source_receipt_id),
                )
                persisted += cursor.rowcount
        self._connection.commit()
        return persisted

    def insert_benchmark_corporate_actions(
        self, *, benchmark_ticker: str, actions: list[CorporateAction],
        raw_artifact_id: str, source_reference: str, source_receipt_id: str | None,
        availability_rule_id: str,
        available_at: datetime | Callable[[CorporateAction], datetime],
    ) -> int:
        """Append compact benchmark actions without polluting the equity master."""
        persisted = 0
        ticker = benchmark_ticker.upper()
        with self._connection.cursor() as cursor:
            for action in actions:
                if action.ticker != ticker:
                    continue
                action_available_at = available_at(action) if callable(available_at) else available_at
                cursor.execute(
                    """INSERT INTO quantrade.benchmark_corporate_actions
                           (benchmark_ticker,provider_action_id,action_type,process_date,effective_date,
                            cash_amount,ratio_numerator,ratio_denominator,currency,available_at,
                            availability_rule_id,ingested_at,raw_artifact_id,source_reference,source_receipt_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'USD',%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (benchmark_ticker,provider_action_id) DO NOTHING""",
                    (
                        ticker, action.provider_action_id, action.action_type, action.process_date,
                        action.effective_date, action.cash_amount, action.ratio_numerator,
                        action.ratio_denominator, action_available_at, availability_rule_id,
                        datetime.now(timezone.utc), raw_artifact_id, source_reference, source_receipt_id,
                    ),
                )
                persisted += cursor.rowcount
        self._connection.commit()
        return persisted


def record_market_source(
    repository: PostgresMarketDataRepository, store: FileRawArtifactStore, payload: bytes,
    retrieved_at: datetime, source_reference: str, *, response_category: str,
    raw_category: str, compact_receipts: bool, parser_version: str, provider: str,
) -> MarketSource:
    """Store either a full raw response or a compact, hash-backed source receipt."""
    if compact_receipts:
        receipt = repository.persist_compact_receipt(
            payload, source_reference, response_category, retrieved_at,
            parser_version=parser_version, provider=provider,
        )
        return MarketSource(receipt.raw_artifact_id, receipt.storage_uri, receipt.source_receipt_id)
    artifact = store.store(payload, retrieved_at, category=raw_category)
    return MarketSource(repository.persist_raw_artifact(artifact, source_reference, provider=provider), artifact.storage_uri)
