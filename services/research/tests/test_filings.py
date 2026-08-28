from pathlib import Path
from datetime import date, datetime, timezone
import sys
import unittest


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from quantrade_research.sec_edgar import (
    daily_master_index_url,
    parse_daily_master_index,
    SecEdgarError,
    merge_filings,
    parse_company_facts,
    parse_submission_history,
    parse_submissions,
    submission_history_names,
)
from quantrade_research.filings import StoredSource
from quantrade_research.ingest_filings import (
    _daily_index_candidates, _daily_index_dates, _fetch_daily_master_index_with_retry, _new_accession_numbers,
    _new_filings, _record_source, _requires_company_facts,
)


class FilingParserTests(unittest.TestCase):
    def test_selects_only_current_universe_ciks_present_in_daily_index(self) -> None:
        payload = b"""Description:           Master Index of EDGAR Dissemination Feed\nLast Data Received:    Aug 26, 2026\nComments:              webmaster@sec.gov\n\nCIK|Company Name|Form Type|Date Filed|File Name\n1045810|NVIDIA CORP|10-Q|2026-08-26|edgar/data/1045810/nvda-20260726.htm\n320193|APPLE INC|8-K|2026-08-26|edgar/data/320193/aapl-20260826.htm\n789019|MICROSOFT CORP|8-K|2026-08-26|edgar/data/789019/msft-20260826.htm\n"""
        records = parse_daily_master_index(payload)
        self.assertEqual(daily_master_index_url(date(2026, 8, 26)), "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/master.20260826.idx")
        self.assertEqual({record.cik for record in records}, {"0001045810", "0000320193", "0000789019"})
        self.assertEqual(
            _daily_index_candidates(["0000320193", "0001045810", "0001652044"], {record.cik for record in records}),
            ["0000320193", "0001045810"],
        )

    def test_keeps_weekend_dates_in_the_discovery_interval(self) -> None:
        self.assertEqual(
            _daily_index_dates(date(2026, 8, 21), date(2026, 8, 24)),
            [date(2026, 8, 21), date(2026, 8, 22), date(2026, 8, 23), date(2026, 8, 24)],
        )

    def test_identifies_only_unseen_current_submission_accessions(self) -> None:
        payload = b'{"filings":{"recent":{"form":["10-Q","8-K","8-K"],"accessionNumber":["0000320193-26-000001","0000320193-26-000002","0000320193-26-000002"],"filingDate":["2026-08-01","2026-08-02","2026-08-02"],"acceptanceDateTime":["2026-08-01T20:15:00Z","2026-08-02T20:15:00Z","2026-08-02T20:15:00Z"],"reportDate":["2026-06-30","",""]}}}'
        filings = parse_submissions(payload)
        self.assertEqual(
            _new_accession_numbers(filings, {"0000320193-26-000001"}),
            ["0000320193-26-000002"],
        )
        self.assertEqual(
            [filing.accession_number for filing in _new_filings(filings, {"0000320193-26-000001"})],
            ["0000320193-26-000002"],
        )

    def test_requests_company_facts_only_for_new_financial_filings(self) -> None:
        filings = parse_submissions(
            b'{"filings":{"recent":{"form":["8-K","10-Q/A"],"accessionNumber":["0000320193-26-000001","0000320193-26-000002"],"filingDate":["2026-08-01","2026-08-02"],"acceptanceDateTime":["2026-08-01T20:15:00Z","2026-08-02T20:15:00Z"],"reportDate":["","2026-06-30"]}}}'
        )
        self.assertEqual([filing.form for filing in filings], ["8-K", "10-Q"])
        self.assertFalse(_requires_company_facts([filings[0]]))
        self.assertTrue(_requires_company_facts([filings[1]]))

    def test_retries_the_daily_index_without_a_cohort_wide_fallback(self) -> None:
        class UnstableClient:
            def __init__(self) -> None:
                self.calls = 0

            def fetch_daily_master_index(self, filing_date: date) -> bytes:
                self.calls += 1
                if self.calls < 3:
                    raise SecEdgarError("SEC returned HTTP 503")
                return b"ready"

        client = UnstableClient()
        pauses: list[float] = []
        self.assertEqual(
            _fetch_daily_master_index_with_retry(
                client, date(2026, 8, 27), attempts=3, retry_seconds=0.25, sleep=pauses.append,
            ),
            b"ready",
        )
        self.assertEqual(client.calls, 3)
        self.assertEqual(pauses, [0.25, 0.5])

    def test_daily_index_failure_is_explicit_after_bounded_retries(self) -> None:
        class UnavailableClient:
            def fetch_daily_master_index(self, filing_date: date) -> bytes:
                raise SecEdgarError("SEC returned HTTP 503")

        with self.assertRaisesRegex(SecEdgarError, "after 2 attempts"):
            _fetch_daily_master_index_with_retry(
                UnavailableClient(), date(2026, 8, 27), attempts=2, retry_seconds=0, sleep=lambda _seconds: None,
            )

    def test_compact_receipt_mode_never_writes_a_payload_file(self) -> None:
        expected = StoredSource("artifact-id", "receipt://sec-edgar/reference/hash", "https://data.sec.gov/example", "receipt-id")

        class Repository:
            def persist_compact_receipt(self, payload, source_reference, response_category, retrieved_at, *, parser_version):
                self.request = (payload, source_reference, response_category, retrieved_at, parser_version)
                return expected

        class FileStore:
            def store(self, *args, **kwargs):
                raise AssertionError("compact receipt mode must not write a payload file")

        repository = Repository()
        result = _record_source(
            repository, FileStore(), b'{"filings":{}}', datetime(2026, 8, 27, tzinfo=timezone.utc),
            "https://data.sec.gov/example", response_category="sec_submissions", raw_category="sec-submissions",
            compact_receipts=True,
        )
        self.assertEqual(result, expected)
        self.assertEqual(repository.request[2], "sec_submissions")
        self.assertEqual(repository.request[4], "sec_edgar_parser_v1")

    def test_links_company_facts_to_submission_acceptance_metadata(self) -> None:
        submissions = b'{"filings":{"recent":{"form":["10-Q"],"accessionNumber":["0000320193-26-000001"],"filingDate":["2026-08-01"],"acceptanceDateTime":["2026-08-01T20:15:00.000Z"],"reportDate":["2026-06-30"]}}}'
        filings = parse_submissions(submissions)
        facts = parse_company_facts(
            b'{"facts":{"us-gaap":{"Assets":{"units":{"USD":[{"accn":"0000320193-26-000001","val":1000,"start":"2026-01-01","end":"2026-06-30","fy":2026,"fp":"Q2"},{"accn":"missing","val":9,"end":"2026-06-30"}]}}}}}',
            {filing.accession_number: filing for filing in filings},
        )
        self.assertEqual(len(filings), 1)
        self.assertEqual(filings[0].accepted_at.isoformat(), "2026-08-01T20:15:00+00:00")
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].accession_number, filings[0].accession_number)
        self.assertEqual(str(facts[0].value), "1000")

    def test_other_forms_are_retained_without_becoming_supported_form_labels(self) -> None:
        payload = b'{"filings":{"recent":{"form":["DEF 14A"],"accessionNumber":["0000320193-26-000002"],"filingDate":["2026-08-01"],"acceptanceDateTime":["2026-08-01T20:15:00Z"],"reportDate":[""]}}}'
        self.assertEqual(parse_submissions(payload)[0].form, "other")

    def test_reads_dated_submission_history_and_merges_it_with_recent_filings(self) -> None:
        recent = b'{"filings":{"recent":{"form":["10-Q"],"accessionNumber":["0000320193-26-000001"],"filingDate":["2026-08-01"],"acceptanceDateTime":["2026-08-01T20:15:00Z"],"reportDate":["2026-06-30"]},"files":[{"name":"CIK0000320193-submissions-001.json"}]}}'
        history = b'{"form":["10-K"],"accessionNumber":["0000320193-21-000001"],"filingDate":["2021-01-29"],"acceptanceDateTime":["2021-01-29T16:30:00Z"],"reportDate":["2020-12-31"]}'
        self.assertEqual(submission_history_names(recent), ["CIK0000320193-submissions-001.json"])
        filings = merge_filings(parse_submissions(recent), parse_submission_history(history))
        self.assertEqual([filing.accession_number for filing in filings], ["0000320193-21-000001", "0000320193-26-000001"])
        self.assertEqual(filings[0].accepted_at.isoformat(), "2021-01-29T16:30:00+00:00")

    def test_rejects_unsafe_submission_history_file_name(self) -> None:
        payload = b'{"filings":{"recent":{"form":[],"accessionNumber":[],"filingDate":[],"acceptanceDateTime":[],"reportDate":[]},"files":[{"name":"../outside.json"}]}}'
        with self.assertRaisesRegex(SecEdgarError, "invalid file name"):
            submission_history_names(payload)


if __name__ == "__main__":
    unittest.main()
