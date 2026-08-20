"""Fail-closed data-quality and point-in-time gates for research inputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable, Protocol


class DataQualityError(ValueError):
    """Raised when inputs cannot safely be used for a dated decision."""


class AvailableRecord(Protocol):
    available_at: datetime


@dataclass(frozen=True, slots=True)
class DailyBarQualityInput:
    security_id: str
    session_date: date
    adjustment_basis: str
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    available_at: datetime


@dataclass(frozen=True, slots=True)
class FilingFactQualityInput:
    security_id: str
    taxonomy: str
    concept: str
    period_end: date
    available_at: datetime


@dataclass(frozen=True, slots=True)
class QualityIssue:
    code: str
    detail: str


@dataclass(frozen=True, slots=True)
class QualityReport:
    issues: tuple[QualityIssue, ...]

    @property
    def publishable(self) -> bool:
        return not self.issues

    def require_publishable(self) -> None:
        if self.issues:
            rendered = "; ".join(f"{issue.code}: {issue.detail}" for issue in self.issues)
            raise DataQualityError(rendered)


def _require_aware_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DataQualityError(f"{label} must include a UTC offset")
    return value.astimezone(timezone.utc)


def assert_available_as_of(records: Iterable[AvailableRecord], decision_at: datetime, label: str) -> None:
    decision = _require_aware_utc(decision_at, "decision_at")
    violations = [record for record in records if _require_aware_utc(record.available_at, "available_at") > decision]
    if violations:
        raise DataQualityError(f"{label} contains {len(violations)} record(s) unavailable at decision_at")


def evaluate_daily_bar_quality(
    bars: Iterable[DailyBarQualityInput],
    required_security_ids: set[str],
    required_session_date: date,
    adjustment_basis: str,
    decision_at: datetime,
) -> QualityReport:
    decision = _require_aware_utc(decision_at, "decision_at")
    issues: list[QualityIssue] = []
    matching = [bar for bar in bars if bar.session_date == required_session_date and bar.adjustment_basis == adjustment_basis]
    by_security: dict[str, list[DailyBarQualityInput]] = {}
    for bar in matching:
        by_security.setdefault(bar.security_id, []).append(bar)
        if min(bar.open_price, bar.high_price, bar.low_price, bar.close_price, bar.volume) < 0:
            issues.append(QualityIssue("invalid_bar_value", f"{bar.security_id} has a negative OHLCV value"))
        if bar.high_price < max(bar.open_price, bar.close_price) or bar.low_price > min(bar.open_price, bar.close_price):
            issues.append(QualityIssue("invalid_ohlc_range", f"{bar.security_id} violates its high/low range"))
        if _require_aware_utc(bar.available_at, "available_at") > decision:
            issues.append(QualityIssue("future_available_at", f"{bar.security_id} became available after the decision"))
    for security_id in sorted(required_security_ids):
        observations = by_security.get(security_id, [])
        if not observations:
            issues.append(QualityIssue("missing_daily_bar", f"{security_id} has no {adjustment_basis} bar for {required_session_date}"))
        elif len(observations) > 1:
            issues.append(QualityIssue("duplicate_daily_bar", f"{security_id} has {len(observations)} bars for one session"))
    return QualityReport(tuple(issues))


def evaluate_filing_fact_quality(
    facts: Iterable[FilingFactQualityInput], decision_at: datetime
) -> QualityReport:
    decision = _require_aware_utc(decision_at, "decision_at")
    issues: list[QualityIssue] = []
    seen: set[tuple[str, str, str, date]] = set()
    for fact in facts:
        identity = (fact.security_id, fact.taxonomy, fact.concept, fact.period_end)
        if identity in seen:
            issues.append(QualityIssue("duplicate_filing_fact", f"duplicate {fact.taxonomy}:{fact.concept} for {fact.security_id}"))
        seen.add(identity)
        if _require_aware_utc(fact.available_at, "available_at") > decision:
            issues.append(QualityIssue("future_available_at", f"{fact.taxonomy}:{fact.concept} is unavailable at the decision"))
    return QualityReport(tuple(issues))
