"""Construct point-in-time research panels from already-normalized inputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable

from .quality import DailyBarQualityInput, DataQualityError, evaluate_daily_bar_quality


@dataclass(frozen=True, slots=True)
class UniverseMembershipInput:
    security_id: str
    as_of_date: date
    available_at: datetime


@dataclass(frozen=True, slots=True)
class FilingFactPanelInput:
    security_id: str
    filing_id: str
    taxonomy: str
    concept: str
    value: Decimal
    period_end: date
    available_at: datetime


@dataclass(frozen=True, slots=True)
class PointInTimePanelRow:
    security_id: str
    session_date: date
    close_price: Decimal
    volume: Decimal
    facts: dict[tuple[str, str], Decimal]


def _as_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DataQualityError(f"{label} must include a UTC offset")
    return value.astimezone(timezone.utc)


def build_point_in_time_panel(
    *,
    memberships: Iterable[UniverseMembershipInput],
    bars: Iterable[DailyBarQualityInput],
    filing_facts: Iterable[FilingFactPanelInput],
    session_date: date,
    decision_at: datetime,
    adjustment_basis: str,
    required_facts: set[tuple[str, str]],
) -> list[PointInTimePanelRow]:
    """Build a complete panel or raise; it never silently excludes bad inputs."""
    decision = _as_utc(decision_at, "decision_at")
    active_memberships = list(memberships)
    issues: list[str] = []
    security_ids: set[str] = set()
    for membership in active_memberships:
        if membership.as_of_date > session_date:
            issues.append(f"membership {membership.security_id} has future as_of_date")
        if _as_utc(membership.available_at, "membership available_at") > decision:
            issues.append(f"membership {membership.security_id} was unavailable at decision_at")
        if membership.security_id in security_ids:
            issues.append(f"duplicate universe membership for {membership.security_id}")
        security_ids.add(membership.security_id)
    if not security_ids:
        issues.append("universe membership is empty")
    if issues:
        raise DataQualityError("; ".join(issues))

    bars_list = list(bars)
    bar_report = evaluate_daily_bar_quality(
        bars_list, security_ids, session_date, adjustment_basis, decision
    )
    bar_report.require_publishable()
    bars_by_security = {
        bar.security_id: bar
        for bar in bars_list
        if bar.session_date == session_date and bar.adjustment_basis == adjustment_basis
    }

    eligible_facts: dict[tuple[str, tuple[str, str]], list[FilingFactPanelInput]] = {}
    for fact in filing_facts:
        if fact.security_id not in security_ids or (fact.taxonomy, fact.concept) not in required_facts:
            continue
        if fact.period_end > session_date or _as_utc(fact.available_at, "fact available_at") > decision:
            continue
        eligible_facts.setdefault((fact.security_id, (fact.taxonomy, fact.concept)), []).append(fact)

    panel: list[PointInTimePanelRow] = []
    missing: list[str] = []
    for security_id in sorted(security_ids):
        selected: dict[tuple[str, str], Decimal] = {}
        for factor_key in required_facts:
            candidates = eligible_facts.get((security_id, factor_key), [])
            if not candidates:
                missing.append(f"{security_id} lacks {factor_key[0]}:{factor_key[1]}")
                continue
            chosen = max(candidates, key=lambda item: (item.period_end, _as_utc(item.available_at, "fact available_at"), item.filing_id))
            selected[factor_key] = chosen.value
        bar = bars_by_security[security_id]
        panel.append(PointInTimePanelRow(security_id, session_date, bar.close_price, bar.volume, selected))
    if missing:
        raise DataQualityError("; ".join(missing))
    return panel
