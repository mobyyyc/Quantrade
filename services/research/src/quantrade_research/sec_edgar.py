"""Minimal, rate-conscious client for SEC EDGAR reference data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import json
import re
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


COMPANY_TICKERS_EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SUBMISSION_HISTORY_URL = "https://data.sec.gov/submissions/{name}"
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
DAILY_MASTER_INDEX_URL = "https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{quarter}/master.{stamp}.idx"

_SUBMISSION_HISTORY_NAME = re.compile(r"^CIK\d{10}-submissions-\d{3}\.json$")

EXCHANGE_MIC_BY_SEC_NAME = {
    "Nasdaq": "XNAS",
    "NYSE": "XNYS",
    "NYSE American": "XASE",
    "NYSE Arca": "ARCX",
    "Cboe BZX": "BATS",
}


class SecEdgarError(ValueError):
    """Raised when SEC reference data is unavailable or malformed."""


class SecEdgarNotFoundError(SecEdgarError):
    """Raised when an SEC resource is absent, such as a non-filing-day index."""


@dataclass(frozen=True, slots=True)
class SecTickerAssociation:
    cik: str
    name: str
    ticker: str
    exchange: str


@dataclass(frozen=True, slots=True)
class SecurityMasterRow:
    cik: str
    issuer_name: str
    ticker: str
    exchange_mic: str
    snapshot_date: date


@dataclass(frozen=True, slots=True)
class SecFilingMetadata:
    accession_number: str
    form: str
    filed_at: datetime
    accepted_at: datetime
    period_end: date | None


@dataclass(frozen=True, slots=True)
class SecFilingFact:
    accession_number: str
    taxonomy: str
    concept: str
    unit: str
    value: Decimal
    period_start: date | None
    period_end: date
    fiscal_year: int | None
    fiscal_period: str | None
    filed_at: datetime


@dataclass(frozen=True, slots=True)
class SecDailyIndexRecord:
    cik: str
    form: str
    filed_on: date
    file_name: str


def parse_company_tickers_exchange(payload: bytes) -> list[SecTickerAssociation]:
    try:
        document: dict[str, Any] = json.loads(payload)
        fields = document["fields"]
        data = document["data"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise SecEdgarError("SEC ticker/exchange payload has an invalid shape") from error

    if fields != ["cik", "name", "ticker", "exchange"] or not isinstance(data, list):
        raise SecEdgarError("SEC ticker/exchange payload fields changed unexpectedly")

    associations: list[SecTickerAssociation] = []
    for row in data:
        if not isinstance(row, list) or len(row) != 4:
            raise SecEdgarError("SEC ticker/exchange payload contains an invalid row")
        cik, name, ticker, exchange = row
        if not all(isinstance(value, (str, int)) for value in (cik, name, ticker)) or exchange is not None and not isinstance(exchange, (str, int)):
            raise SecEdgarError("SEC ticker/exchange payload contains a non-scalar value")
        cik_text = str(cik).zfill(10)
        if not cik_text.isdigit() or not str(name).strip() or not str(ticker).strip():
            raise SecEdgarError("SEC ticker/exchange payload contains an invalid association")
        associations.append(
            SecTickerAssociation(cik_text, str(name).strip(), str(ticker).strip(), str(exchange or "").strip())
        )
    return associations


def normalize_security_master(
    associations: list[SecTickerAssociation], snapshot_date: date
) -> tuple[list[SecurityMasterRow], list[SecTickerAssociation]]:
    rows: list[SecurityMasterRow] = []
    unmapped: list[SecTickerAssociation] = []
    for association in associations:
        exchange_mic = EXCHANGE_MIC_BY_SEC_NAME.get(association.exchange)
        if exchange_mic is None:
            unmapped.append(association)
            continue
        rows.append(
            SecurityMasterRow(
                cik=association.cik,
                issuer_name=association.name,
                ticker=association.ticker.upper(),
                exchange_mic=exchange_mic,
                snapshot_date=snapshot_date,
            )
        )
    return rows, unmapped


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise SecEdgarError("SEC filing timestamp is missing")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _optional_date(value: object) -> date | None:
    return date.fromisoformat(value) if isinstance(value, str) and value else None


def _parse_submission_rows(rows: object) -> list[SecFilingMetadata]:
    try:
        forms, accessions, filed, accepted, reports = (
            rows["form"], rows["accessionNumber"], rows["filingDate"],
            rows["acceptanceDateTime"], rows["reportDate"],
        )
    except (KeyError, TypeError) as error:
        raise SecEdgarError("SEC submissions payload columns are invalid") from error
    if not all(isinstance(column, list) for column in (forms, accessions, filed, accepted, reports)):
        raise SecEdgarError("SEC submissions payload columns are invalid")
    filings: list[SecFilingMetadata] = []
    for form, accession, filing_date, acceptance, report_date in zip(forms, accessions, filed, accepted, reports, strict=True):
        if not isinstance(accession, str) or not isinstance(form, str):
            raise SecEdgarError("SEC submissions payload contains an invalid filing")
        filings.append(SecFilingMetadata(accession, form if form in {"10-K", "10-Q", "8-K", "20-F", "40-F"} else "other", _timestamp(filing_date + "T00:00:00Z"), _timestamp(acceptance), _optional_date(report_date)))
    return filings


def parse_submissions(payload: bytes) -> list[SecFilingMetadata]:
    """Parse the current submissions payload's `filings.recent` records."""
    try:
        recent = json.loads(payload)["filings"]["recent"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise SecEdgarError("SEC submissions payload has an invalid shape") from error
    return _parse_submission_rows(recent)


def daily_master_index_url(filing_date: date) -> str:
    quarter = (filing_date.month - 1) // 3 + 1
    return DAILY_MASTER_INDEX_URL.format(
        year=filing_date.year,
        quarter=quarter,
        stamp=filing_date.strftime("%Y%m%d"),
    )


def parse_daily_master_index(payload: bytes) -> list[SecDailyIndexRecord]:
    """Parse the SEC daily master index after its pipe-delimited header."""
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise SecEdgarError("SEC daily master index is not UTF-8") from error

    header_index = next((
        index for index, line in enumerate(lines)
        if line.strip() == "CIK|Company Name|Form Type|Date Filed|File Name"
    ), None)
    if header_index is None:
        raise SecEdgarError("SEC daily master index header is missing")

    records: list[SecDailyIndexRecord] = []
    for line in lines[header_index + 1:]:
        if not line.strip():
            continue
        fields = line.split("|")
        if len(fields) != 5:
            raise SecEdgarError("SEC daily master index contains an invalid row")
        cik, _issuer_name, form, filed_on, file_name = fields
        cik = cik.strip().zfill(10)
        if not cik.isdigit() or not form.strip() or not file_name.strip():
            raise SecEdgarError("SEC daily master index contains an invalid filing")
        try:
            records.append(SecDailyIndexRecord(cik, form.strip(), date.fromisoformat(filed_on.strip()), file_name.strip()))
        except ValueError as error:
            raise SecEdgarError("SEC daily master index contains an invalid filing date") from error
    return records


def submission_history_names(payload: bytes) -> list[str]:
    """Return validated dated submission-history file names in SEC-provided order."""
    try:
        files = json.loads(payload)["filings"].get("files", [])
    except (json.JSONDecodeError, KeyError, AttributeError, TypeError) as error:
        raise SecEdgarError("SEC submissions history references have an invalid shape") from error
    if not isinstance(files, list):
        raise SecEdgarError("SEC submissions history references must be a list")
    names: list[str] = []
    for item in files:
        name = item.get("name") if isinstance(item, dict) else None
        if not isinstance(name, str) or not _SUBMISSION_HISTORY_NAME.fullmatch(name):
            raise SecEdgarError("SEC submissions history contains an invalid file name")
        names.append(name)
    return names


def parse_submission_history(payload: bytes) -> list[SecFilingMetadata]:
    """Parse a dated SEC submission-history file, which stores records at its top level."""
    try:
        rows = json.loads(payload)
    except json.JSONDecodeError as error:
        raise SecEdgarError("SEC submission-history payload is not valid JSON") from error
    return _parse_submission_rows(rows)


def merge_filings(*groups: list[SecFilingMetadata]) -> list[SecFilingMetadata]:
    """Deduplicate SEC history while rejecting conflicting accession metadata."""
    merged: dict[str, SecFilingMetadata] = {}
    for group in groups:
        for filing in group:
            existing = merged.get(filing.accession_number)
            if existing is not None and existing != filing:
                raise SecEdgarError(
                    f"SEC submissions disagree about accession {filing.accession_number}"
                )
            merged[filing.accession_number] = filing
    return sorted(merged.values(), key=lambda filing: (filing.accepted_at, filing.accession_number))


def parse_company_facts(payload: bytes, filings_by_accession: dict[str, SecFilingMetadata]) -> list[SecFilingFact]:
    try:
        taxonomies = json.loads(payload)["facts"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise SecEdgarError("SEC company-facts payload has an invalid shape") from error
    facts: list[SecFilingFact] = []
    if not isinstance(taxonomies, dict):
        raise SecEdgarError("SEC company-facts taxonomy collection is invalid")
    for taxonomy, concepts in taxonomies.items():
        if not isinstance(concepts, dict):
            continue
        for concept, definition in concepts.items():
            units = definition.get("units", {}) if isinstance(definition, dict) else {}
            if not isinstance(units, dict):
                continue
            for unit, observations in units.items():
                if not isinstance(observations, list):
                    continue
                for observation in observations:
                    if not isinstance(observation, dict):
                        continue
                    accession = observation.get("accn")
                    filing = filings_by_accession.get(accession) if isinstance(accession, str) else None
                    if filing is None or not observation.get("end"):
                        continue
                    try:
                        fiscal_year = int(observation["fy"]) if observation.get("fy") is not None else None
                        if fiscal_year is not None and fiscal_year < 1900:
                            fiscal_year = None
                        facts.append(SecFilingFact(accession, str(taxonomy), str(concept), str(unit), Decimal(str(observation["val"])), _optional_date(observation.get("start")), date.fromisoformat(str(observation["end"])), fiscal_year, str(observation["fp"]) if observation.get("fp") in {"FY", "Q1", "Q2", "Q3", "Q4"} else None, filing.filed_at))
                    except (KeyError, ValueError, ArithmeticError) as error:
                        raise SecEdgarError("SEC company-facts observation is invalid") from error
    return facts


class SecEdgarClient:
    def __init__(self, user_agent: str, timeout_seconds: float = 30.0) -> None:
        if not user_agent.strip():
            raise SecEdgarError("a descriptive SEC user agent is required")
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds

    def fetch_company_tickers_exchange(self) -> bytes:
        return self._fetch(COMPANY_TICKERS_EXCHANGE_URL)

    def fetch_submissions(self, cik: str) -> bytes:
        return self._fetch(SUBMISSIONS_URL.format(cik=cik.zfill(10)))

    def fetch_submission_history(self, name: str) -> bytes:
        if not _SUBMISSION_HISTORY_NAME.fullmatch(name):
            raise SecEdgarError("invalid SEC submission-history file name")
        return self._fetch(SUBMISSION_HISTORY_URL.format(name=name))

    def fetch_company_facts(self, cik: str) -> bytes:
        return self._fetch(COMPANY_FACTS_URL.format(cik=cik.zfill(10)))

    def fetch_daily_master_index(self, filing_date: date) -> bytes:
        return self._fetch(daily_master_index_url(filing_date))

    def _fetch(self, url: str) -> bytes:
        request = Request(url, headers={"Accept": "application/json", "User-Agent": self._user_agent})
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                if response.status != 200:
                    raise SecEdgarError(f"SEC returned HTTP {response.status}")
                return response.read()
        except HTTPError as error:
            if error.code == 404:
                raise SecEdgarNotFoundError(f"SEC resource is unavailable: {url}") from error
            raise SecEdgarError(f"SEC returned HTTP {error.code}: {url}") from error
