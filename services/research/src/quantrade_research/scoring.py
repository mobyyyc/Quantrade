"""Idempotent end-of-day score snapshot generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable, Protocol
from zoneinfo import ZoneInfo

from .baseline import CompositeBaselineScore
from .quality import DataQualityError


TORONTO = ZoneInfo("America/Toronto")
PROTOCOL_VERSION = "0.1"


@dataclass(frozen=True, slots=True)
class GeneratedScoreSnapshot:
    security_id: str
    score_date: date
    decision_at: datetime
    published_at: datetime
    score: Decimal
    rank: int | None
    eligible: bool
    signal: str
    model_version: str
    feature_version: str
    protocol_version: str
    data_cutoff_at: datetime
    data_capability_tier: str
    unavailable_reason: str | None

    def identity(self) -> tuple[str, datetime, str, str, str]:
        return (
            self.security_id,
            self.decision_at,
            self.model_version,
            self.feature_version,
            self.protocol_version,
        )


class ScoreSnapshotRepository(Protocol):
    def get(self, identity: tuple[str, datetime, str, str, str]) -> GeneratedScoreSnapshot | None: ...

    def insert_if_absent(self, snapshot: GeneratedScoreSnapshot) -> bool: ...


class InMemoryScoreSnapshotRepository:
    def __init__(self) -> None:
        self._snapshots: dict[tuple[str, datetime, str, str, str], GeneratedScoreSnapshot] = {}

    def get(self, identity: tuple[str, datetime, str, str, str]) -> GeneratedScoreSnapshot | None:
        return self._snapshots.get(identity)

    def insert_if_absent(self, snapshot: GeneratedScoreSnapshot) -> bool:
        if snapshot.identity() in self._snapshots:
            return False
        self._snapshots[snapshot.identity()] = snapshot
        return True


class PostgresScoreSnapshotRepository:
    """PostgreSQL persistence that uses the score-snapshot uniqueness constraint."""

    def __init__(self, database_url: str) -> None:
        try:
            import psycopg
        except ImportError as error:  # pragma: no cover
            raise RuntimeError("Install quantrade-research dependencies before score persistence") from error
        self._connection = psycopg.connect(database_url)

    def close(self) -> None:
        self._connection.close()

    def get(self, identity: tuple[str, datetime, str, str, str]) -> GeneratedScoreSnapshot | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT security_id::text, score_date, decision_at, published_at, score, rank, eligible, signal,
                          model_version, feature_version, protocol_version, data_cutoff_at,
                          data_capability_tier, unavailable_reason
                   FROM quantrade.score_snapshots
                   WHERE security_id = %s AND decision_at = %s AND model_version = %s
                     AND feature_version = %s AND protocol_version = %s""",
                identity,
            )
            row = cursor.fetchone()
        return GeneratedScoreSnapshot(*row) if row is not None else None

    def insert_if_absent(self, snapshot: GeneratedScoreSnapshot) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO quantrade.score_snapshots
                   (security_id, score_date, decision_at, published_at, score, rank, eligible, signal,
                    model_version, feature_version, protocol_version, data_cutoff_at,
                    data_capability_tier, unavailable_reason)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (security_id, decision_at, model_version, feature_version, protocol_version)
                   DO NOTHING""",
                (
                    snapshot.security_id, snapshot.score_date, snapshot.decision_at,
                    snapshot.published_at, snapshot.score, snapshot.rank, snapshot.eligible,
                    snapshot.signal, snapshot.model_version, snapshot.feature_version,
                    snapshot.protocol_version, snapshot.data_cutoff_at,
                    snapshot.data_capability_tier, snapshot.unavailable_reason,
                ),
            )
            inserted = cursor.rowcount == 1
        self._connection.commit()
        return inserted


def _validate_schedule(score_date: date, decision_at: datetime, data_cutoff_at: datetime, manual: bool) -> None:
    if decision_at.tzinfo is None or decision_at.utcoffset() is None:
        raise DataQualityError("decision timestamp must include a UTC offset")
    if data_cutoff_at.tzinfo is None or data_cutoff_at.utcoffset() is None:
        raise DataQualityError("data cutoff timestamp must include a UTC offset")
    local_decision = decision_at.astimezone(TORONTO)
    if local_decision.date() != score_date:
        raise DataQualityError("score decision timestamp must be on the score date in America/Toronto")
    if manual:
        if local_decision.hour < 16:
            raise DataQualityError("manual end-of-day scores can run only after the regular market close")
    elif (local_decision.hour, local_decision.minute) != (20, 0):
        raise DataQualityError("scheduled end-of-day scores must be generated at 8:00 p.m. America/Toronto")
    if data_cutoff_at > decision_at:
        raise DataQualityError("data cutoff cannot be after the score decision timestamp")


def generate_end_of_day_scores(
    baseline_scores: Iterable[CompositeBaselineScore],
    repository: ScoreSnapshotRepository,
    *,
    score_date: date,
    decision_at: datetime,
    published_at: datetime,
    data_cutoff_at: datetime,
    data_capability_tier: str,
    protocol_version: str = PROTOCOL_VERSION,
    manual: bool = False,
) -> tuple[GeneratedScoreSnapshot, ...]:
    """Generate idempotent score snapshots or reject conflicting repeats."""
    _validate_schedule(score_date, decision_at, data_cutoff_at, manual)
    if data_capability_tier not in ("A", "B", "C"):
        raise DataQualityError("data capability tier must be A, B, or C")
    if published_at.tzinfo is None or published_at.utcoffset() is None:
        raise DataQualityError("published timestamp must include a UTC offset")
    source = list(baseline_scores)
    if not source:
        raise DataQualityError("score generation requires at least one baseline score")
    if any(score.formation_date != score_date for score in source):
        raise DataQualityError("baseline scores must use the requested score date")
    if len({score.security_id for score in source}) != len(source):
        raise DataQualityError("baseline scores must be unique by security")
    eligible = [score for score in source if score.eligible and score.display_score is not None]
    eligible.sort(key=lambda score: (-score.display_score, score.security_id))
    ranks = {score.security_id: index for index, score in enumerate(eligible, start=1)}
    snapshots: list[GeneratedScoreSnapshot] = []
    for score in sorted(source, key=lambda item: item.security_id):
        snapshot = GeneratedScoreSnapshot(
            score.security_id,
            score_date,
            decision_at,
            published_at,
            score.display_score if score.display_score is not None else Decimal("0"),
            ranks.get(score.security_id),
            score.eligible,
            "neutral" if score.eligible else "unavailable",
            score.model_version,
            score.feature_registry_hash,
            protocol_version,
            data_cutoff_at,
            data_capability_tier,
            score.unavailable_reason,
        )
        existing = repository.get(snapshot.identity())
        if existing is not None:
            if existing != snapshot:
                different = [
                    field for field in GeneratedScoreSnapshot.__dataclass_fields__
                    if getattr(existing, field) != getattr(snapshot, field)
                ]
                raise DataQualityError(
                    f"conflicting score snapshot already exists for {snapshot.security_id}: "
                    + ",".join(different)
                )
            snapshots.append(existing)
            continue
        if repository.insert_if_absent(snapshot):
            snapshots.append(snapshot)
            continue
        existing = repository.get(snapshot.identity())
        if existing != snapshot:
            raise DataQualityError(f"conflicting concurrent score snapshot for {snapshot.security_id}")
        snapshots.append(existing)
    return tuple(snapshots)
