from datetime import date, datetime, timezone
from pathlib import Path
import sys
import unittest


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from quantrade_research.sec_edgar import (
    SecEdgarError,
    normalize_security_master,
    parse_company_tickers_exchange,
)
from quantrade_research.security_master import (
    RawArtifact,
    persist_security_master_snapshot,
)


class FakeSecurityMasterRepository:
    def __init__(self) -> None:
        self.persisted_rows = []
        self.closed_ciks = []

    def persist_raw_artifact(self, artifact: RawArtifact, source_reference: str) -> str:
        self.artifact = artifact
        self.source_reference = source_reference
        return "artifact-1"

    def upsert_security_master_row(self, row, raw_artifact_id, source_reference, ingested_at) -> None:
        self.persisted_rows.append((row, raw_artifact_id, source_reference, ingested_at))

    def close_missing_sec_listings(self, active_ciks, snapshot_date) -> int:
        self.closed_ciks = active_ciks
        self.snapshot_date = snapshot_date
        return 2


class SecurityMasterTests(unittest.TestCase):
    def test_parses_and_normalizes_sec_exchange_fixture(self) -> None:
        payload = b'{"fields":["cik","name","ticker","exchange"],"data":[[320193,"APPLE INC","AAPL","Nasdaq"],[1652044,"Alphabet Inc.","GOOGL","Nasdaq"],[1,"Unknown Corp","UNM","Other"]]}'
        associations = parse_company_tickers_exchange(payload)
        rows, unmapped = normalize_security_master(associations, date(2026, 8, 20))

        self.assertEqual(rows[0].cik, "0000320193")
        self.assertEqual(rows[0].exchange_mic, "XNAS")
        self.assertEqual(rows[1].ticker, "GOOGL")
        self.assertEqual([row.ticker for row in unmapped], ["UNM"])

    def test_rejects_changed_sec_payload_shape(self) -> None:
        with self.assertRaises(SecEdgarError):
            parse_company_tickers_exchange(b'{"fields":["cik"],"data":[]}')

    def test_allows_a_missing_exchange_as_an_unmapped_row(self) -> None:
        associations = parse_company_tickers_exchange(b'{"fields":["cik","name","ticker","exchange"],"data":[[320193,"APPLE INC","AAPL",null]]}')
        rows, unmapped = normalize_security_master(associations, date(2026, 8, 20))
        self.assertFalse(rows)
        self.assertEqual(unmapped[0].ticker, "AAPL")

    def test_persists_snapshot_with_auditable_report(self) -> None:
        payload = b'{"fields":["cik","name","ticker","exchange"],"data":[[320193,"APPLE INC","AAPL","Nasdaq"]]}'
        rows, unmapped = normalize_security_master(
            parse_company_tickers_exchange(payload), date(2026, 8, 20)
        )
        repository = FakeSecurityMasterRepository()
        report = persist_security_master_snapshot(
            repository,
            RawArtifact(
                storage_uri="file:///artifacts/security-master.json",
                content_sha256="a" * 64,
                retrieved_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
            ),
            "https://www.sec.gov/files/company_tickers_exchange.json",
            rows,
            len(unmapped),
        )

        self.assertEqual(report.normalized_rows, 1)
        self.assertEqual(report.closed_listings, 2)
        self.assertEqual(repository.closed_ciks, ["0000320193"])
        self.assertIn("raw_artifact_uri=file:///artifacts/security-master.json", report.manifest_note())


if __name__ == "__main__":
    unittest.main()
