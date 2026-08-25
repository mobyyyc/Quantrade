"""Register immutable research cohorts for historical, point-in-time studies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


CURRENT_SURVIVORS_COHORT = "sp500_current_survivors_v1"
VERIFIED_PIT_COHORT = "sp500_verified_pit_v1"
CURRENT_SURVIVORS_SOURCE_UNIVERSE = "sp500"
CURRENT_SURVIVORS_PROVENANCE_NOTE = (
    "Fixed cohort copied from a current S&P 500 snapshot. It is survivorship-biased, "
    "uses a static current sector mapping, and must never be described as historical S&P 500 membership."
)


class HistoricalCohortError(ValueError):
    """Raised when a historical cohort cannot be registered faithfully."""


@dataclass(frozen=True, slots=True)
class SourceUniverseSnapshot:
    universe_snapshot_id: str
    as_of_date: date
    constituent_count: int
    raw_artifact_uri: str


@dataclass(frozen=True, slots=True)
class HistoricalCohortReport:
    cohort_code: str
    source_universe_code: str
    source_as_of_date: date
    constituent_count: int
    data_capability_tier: str
    survivorship_biased: bool
    sector_classification_point_in_time: bool
    raw_artifact_uri: str

    def manifest_note(self) -> str:
        return (
            f"cohort={self.cohort_code}; source_universe={self.source_universe_code}; "
            f"source_as_of_date={self.source_as_of_date.isoformat()}; constituents={self.constituent_count}; "
            f"tier={self.data_capability_tier}; survivorship_biased={self.survivorship_biased}; "
            f"sector_classification_point_in_time={self.sector_classification_point_in_time}"
        )


class HistoricalCohortRepository(Protocol):
    def latest_universe_snapshot(self, universe_code: str) -> SourceUniverseSnapshot: ...

    def register_current_survivors_cohort(
        self, *, cohort_code: str, source_snapshot: SourceUniverseSnapshot, provenance_note: str,
    ) -> None: ...


def register_current_survivors_cohort(
    repository: HistoricalCohortRepository,
    *, source_universe_code: str = CURRENT_SURVIVORS_SOURCE_UNIVERSE,
) -> HistoricalCohortReport:
    if source_universe_code != CURRENT_SURVIVORS_SOURCE_UNIVERSE:
        raise HistoricalCohortError(
            f"{CURRENT_SURVIVORS_COHORT} must be copied from {CURRENT_SURVIVORS_SOURCE_UNIVERSE}, not {source_universe_code}"
        )
    snapshot = repository.latest_universe_snapshot(source_universe_code)
    if snapshot.constituent_count != 500:
        raise HistoricalCohortError(
            f"{CURRENT_SURVIVORS_COHORT} requires exactly 500 current constituents; found {snapshot.constituent_count}"
        )
    repository.register_current_survivors_cohort(
        cohort_code=CURRENT_SURVIVORS_COHORT,
        source_snapshot=snapshot,
        provenance_note=CURRENT_SURVIVORS_PROVENANCE_NOTE,
    )
    return HistoricalCohortReport(
        cohort_code=CURRENT_SURVIVORS_COHORT,
        source_universe_code=source_universe_code,
        source_as_of_date=snapshot.as_of_date,
        constituent_count=snapshot.constituent_count,
        data_capability_tier="B",
        survivorship_biased=True,
        sector_classification_point_in_time=False,
        raw_artifact_uri=snapshot.raw_artifact_uri,
    )


class PostgresHistoricalCohortRepository:
    """PostgreSQL writer that makes an existing current membership snapshot a fixed cohort."""

    def __init__(self, database_url: str) -> None:
        try:
            import psycopg
        except ImportError as error:  # pragma: no cover
            raise RuntimeError("Install quantrade-research dependencies before cohort registration") from error
        self._connection = psycopg.connect(database_url)

    def close(self) -> None:
        self._connection.close()

    def latest_universe_snapshot(self, universe_code: str) -> SourceUniverseSnapshot:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT snapshot.universe_snapshot_id::text, snapshot.as_of_date,
                          COUNT(membership.security_id)::integer, artifact.storage_uri
                   FROM quantrade.universe_snapshots AS snapshot
                   JOIN quantrade.universe_memberships AS membership
                     ON membership.universe_snapshot_id = snapshot.universe_snapshot_id
                   JOIN quantrade.raw_artifacts AS artifact
                     ON artifact.raw_artifact_id = snapshot.raw_artifact_id
                   WHERE snapshot.universe_code = %s
                   GROUP BY snapshot.universe_snapshot_id, snapshot.as_of_date, artifact.storage_uri
                   ORDER BY snapshot.as_of_date DESC, snapshot.universe_snapshot_id DESC
                   LIMIT 1""",
                (universe_code,),
            )
            row = cursor.fetchone()
        if row is None:
            raise HistoricalCohortError(f"no source snapshot exists for universe {universe_code}")
        return SourceUniverseSnapshot(str(row[0]), row[1], int(row[2]), str(row[3]))

    def register_current_survivors_cohort(
        self, *, cohort_code: str, source_snapshot: SourceUniverseSnapshot, provenance_note: str,
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO quantrade.research_cohorts
                       (cohort_code, cohort_kind, source_universe_snapshot_id, data_capability_tier,
                        historical_membership_verified, survivorship_biased,
                        sector_classification_point_in_time, status, provenance_note)
                   VALUES (%s, 'current_survivors', %s, 'B', false, true, false, 'active', %s)
                   ON CONFLICT (cohort_code) DO NOTHING
                   RETURNING research_cohort_id::text""",
                (cohort_code, source_snapshot.universe_snapshot_id, provenance_note),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    """SELECT research_cohort_id::text, source_universe_snapshot_id::text, cohort_kind,
                              data_capability_tier, historical_membership_verified, survivorship_biased,
                              sector_classification_point_in_time
                       FROM quantrade.research_cohorts WHERE cohort_code = %s""",
                    (cohort_code,),
                )
                existing = cursor.fetchone()
                assert existing is not None
                expected = (
                    source_snapshot.universe_snapshot_id, "current_survivors", "B", False, True, False,
                )
                if tuple(str(value) if index == 0 and value is not None else value for index, value in enumerate(existing[1:])) != expected:
                    raise HistoricalCohortError(f"existing cohort {cohort_code} has incompatible provenance")
                cohort_id = str(existing[0])
            else:
                cohort_id = str(row[0])
            cursor.execute(
                """INSERT INTO quantrade.research_cohort_memberships (research_cohort_id, security_id)
                   SELECT %s, security_id FROM quantrade.universe_memberships
                   WHERE universe_snapshot_id = %s
                   ON CONFLICT DO NOTHING""",
                (cohort_id, source_snapshot.universe_snapshot_id),
            )
        self._connection.commit()
