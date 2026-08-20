"""Locked holdout governance and append-only research experiment records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .quality import DataQualityError


@dataclass(frozen=True, slots=True)
class HoldoutPeriod:
    protocol_version: str
    start_date: date
    end_date: date
    locked_at: datetime
    rationale: str

    def __post_init__(self) -> None:
        if not self.protocol_version.strip() or not self.rationale.strip():
            raise DataQualityError("holdout protocol version and rationale are required")
        if self.start_date > self.end_date:
            raise DataQualityError("holdout start date must not be after its end date")
        if self.locked_at.tzinfo is None or self.locked_at.utcoffset() is None:
            raise DataQualityError("holdout lock timestamp must include a UTC offset")


@dataclass(frozen=True, slots=True)
class ExperimentRecord:
    experiment_id: str
    created_at: datetime
    protocol_version: str
    model_version: str
    feature_registry_hash: str
    training_end_date: date
    validation_end_date: date
    result_uri: str

    def __post_init__(self) -> None:
        if not all((self.experiment_id.strip(), self.protocol_version.strip(), self.model_version.strip(), self.result_uri.strip())):
            raise DataQualityError("experiment identity, versions, and result URI are required")
        if len(self.feature_registry_hash) != 64:
            raise DataQualityError("experiment feature registry hash must be SHA-256")
        if self.training_end_date > self.validation_end_date:
            raise DataQualityError("experiment training end must not be after validation end")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise DataQualityError("experiment timestamp must include a UTC offset")


class ExperimentLog:
    """An append-only log that prevents final-holdout contamination."""

    def __init__(self, holdout: HoldoutPeriod) -> None:
        self.holdout = holdout
        self._records: dict[str, ExperimentRecord] = {}

    def append(self, record: ExperimentRecord) -> None:
        if record.protocol_version != self.holdout.protocol_version:
            raise DataQualityError("experiment protocol version does not match the locked holdout")
        if record.validation_end_date >= self.holdout.start_date:
            raise DataQualityError("experiment validation reaches the locked final holdout")
        if record.experiment_id in self._records:
            raise DataQualityError(f"experiment already recorded: {record.experiment_id}")
        self._records[record.experiment_id] = record

    def records(self) -> tuple[ExperimentRecord, ...]:
        return tuple(sorted(self._records.values(), key=lambda record: (record.created_at, record.experiment_id)))
