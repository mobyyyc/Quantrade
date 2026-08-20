"""PostgreSQL persistence for normalized Alpaca daily bars and corporate actions."""

from __future__ import annotations

from datetime import datetime, timezone
import json

from .alpaca import AlpacaCorporateAction, AlpacaDailyBar
from .security_master import RawArtifact


class PostgresMarketDataRepository:
    def __init__(self, database_url: str) -> None:
        try:
            import psycopg
        except ImportError as error:  # pragma: no cover
            raise RuntimeError("Install quantrade-research dependencies before database ingestion") from error
        self._connection = psycopg.connect(database_url)

    def close(self) -> None:
        self._connection.close()

    def persist_raw_artifact(self, artifact: RawArtifact, source_reference: str) -> str:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO quantrade.raw_artifacts
                    (provider, source_reference, storage_uri, retrieved_at, content_sha256)
                VALUES ('alpaca', %s, %s, %s, %s)
                ON CONFLICT (storage_uri) DO UPDATE SET storage_uri = EXCLUDED.storage_uri
                RETURNING raw_artifact_id
                """,
                (source_reference, artifact.storage_uri, artifact.retrieved_at, artifact.content_sha256),
            )
            identifier = str(cursor.fetchone()[0])
        self._connection.commit()
        return identifier

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
            raise ValueError(f"no active security-master listing for {ticker} on {on_date}")
        return row[0]

    def upsert_daily_bars(self, bars: list[AlpacaDailyBar], adjustment_basis: str, raw_artifact_id: str, source_reference: str, available_at: datetime) -> int:
        with self._connection.cursor() as cursor:
            for bar in bars:
                security_id = self._security_id(cursor, bar.ticker, bar.session_date)
                cursor.execute(
                    """
                    INSERT INTO quantrade.daily_price_bars
                        (security_id, session_date, session, currency, open_price, high_price, low_price,
                         close_price, volume, adjustment_basis, observed_at, available_at, ingested_at,
                         raw_artifact_id, source_reference)
                    VALUES (%s, %s, 'regular', 'USD', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (security_id, session_date, session, adjustment_basis)
                    DO UPDATE SET open_price = EXCLUDED.open_price, high_price = EXCLUDED.high_price,
                        low_price = EXCLUDED.low_price, close_price = EXCLUDED.close_price,
                        volume = EXCLUDED.volume, observed_at = EXCLUDED.observed_at,
                        available_at = EXCLUDED.available_at, ingested_at = EXCLUDED.ingested_at,
                        raw_artifact_id = EXCLUDED.raw_artifact_id, source_reference = EXCLUDED.source_reference
                    """,
                    (security_id, bar.session_date, bar.open_price, bar.high_price, bar.low_price,
                     bar.close_price, bar.volume, adjustment_basis, bar.observed_at, available_at,
                     datetime.now(timezone.utc), raw_artifact_id, source_reference),
                )
        self._connection.commit()
        return len(bars)

    def upsert_corporate_actions(self, actions: list[AlpacaCorporateAction], raw_artifact_id: str, source_reference: str, available_at: datetime) -> int:
        with self._connection.cursor() as cursor:
            for action in actions:
                security_id = self._security_id(cursor, action.ticker, action.effective_date or action.process_date)
                cursor.execute(
                    """
                    INSERT INTO quantrade.corporate_actions
                        (security_id, provider_action_id, action_type, process_date, effective_date,
                         cash_amount, ratio_numerator, ratio_denominator, currency, available_at,
                         ingested_at, raw_artifact_id, source_reference, provider_payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'USD', %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (provider_action_id)
                    DO UPDATE SET available_at = EXCLUDED.available_at, ingested_at = EXCLUDED.ingested_at,
                        raw_artifact_id = EXCLUDED.raw_artifact_id, source_reference = EXCLUDED.source_reference,
                        provider_payload = EXCLUDED.provider_payload
                    """,
                    (security_id, action.provider_action_id, action.action_type, action.process_date,
                     action.effective_date, action.cash_amount, action.ratio_numerator,
                     action.ratio_denominator, available_at, datetime.now(timezone.utc), raw_artifact_id,
                     source_reference, json.dumps(action.payload, sort_keys=True)),
                )
        self._connection.commit()
        return len(actions)
