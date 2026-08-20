"""Versioned, secret-safe manifests for reproducible research runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Literal, Sequence
from uuid import uuid4

from .config import Settings


RunKind = Literal["ingestion", "score", "backtest"]
RunStatus = Literal["started", "completed", "failed", "skipped"]
_GIT_REVISION = re.compile(r"^[0-9a-f]{7,64}$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("manifest timestamps must include a UTC offset")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class SourceInput:
    provider: Literal["sec_edgar", "alpaca", "fred", "alfred", "manual"]
    source_reference: str
    raw_artifact_uris: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.source_reference:
            raise ValueError("source_reference is required")
        if not self.raw_artifact_uris:
            raise ValueError("at least one raw artifact URI is required")


@dataclass(frozen=True, slots=True)
class RunManifest:
    manifest_version: Literal["v1"]
    run_id: str
    run_kind: RunKind
    status: RunStatus
    created_at: str
    code_revision: str
    data_capability_tier: Literal["A", "B", "C"]
    configuration_fingerprint: str
    configuration: dict[str, object]
    source_inputs: tuple[SourceInput, ...]
    decision_at: str | None = None
    note: str | None = None

    @classmethod
    def create(
        cls,
        *,
        settings: Settings,
        run_kind: RunKind,
        code_revision: str,
        data_capability_tier: Literal["A", "B", "C"],
        source_inputs: Sequence[SourceInput],
        status: RunStatus = "started",
        decision_at: datetime | None = None,
        note: str | None = None,
        created_at: datetime | None = None,
    ) -> "RunManifest":
        if not _GIT_REVISION.fullmatch(code_revision):
            raise ValueError("code_revision must be a 7-to-64 character lowercase Git SHA")
        if run_kind in {"score", "backtest"} and decision_at is None:
            raise ValueError("decision_at is required for score and backtest runs")

        return cls(
            manifest_version="v1",
            run_id=str(uuid4()),
            run_kind=run_kind,
            status=status,
            created_at=_iso_utc(created_at or _utc_now()),
            code_revision=code_revision,
            data_capability_tier=data_capability_tier,
            configuration_fingerprint=settings.configuration_fingerprint(),
            configuration=settings.redacted_summary(),
            source_inputs=tuple(source_inputs),
            decision_at=_iso_utc(decision_at) if decision_at else None,
            note=note,
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
