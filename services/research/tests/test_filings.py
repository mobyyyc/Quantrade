from pathlib import Path
import sys
import unittest


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from quantrade_research.sec_edgar import parse_company_facts, parse_submissions


class FilingParserTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
