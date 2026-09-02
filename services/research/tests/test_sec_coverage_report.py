from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quantrade_research.sec_coverage_report import (
    Company, Filing, SELECTED_CONCEPTS, build_report, publish_report,
)
from quantrade_research.sec_fact_resolver import LEGACY_AVAILABILITY_RULE, ResolvedSecFact


ACCEPTED = datetime(2026, 8, 1, 20, tzinfo=timezone.utc)
CUTOFF = ACCEPTED + timedelta(days=1)
COMPANIES = [Company('one', 'One Corp', ('ONE',), ('0000000001',)), Company('two', 'Two Corp', (), ())]
FILING = Filing('f1', 'one', 'a1', '10-Q', ACCEPTED, date(2026, 6, 30))
FACT = ResolvedSecFact(
    'key1', 'f1', 'one', 'a1', '10-Q', False, 'us-gaap', 'Assets', 'USD', Decimal('100'),
    None, date(2026, 6, 30), 2026, 'Q2', ACCEPTED, None, ACCEPTED + timedelta(minutes=5),
    LEGACY_AVAILABILITY_RULE, 'https://example.test/f1', None,
)


def report(filings=(FILING,), facts=(FACT,), **kwargs):
    return build_report(companies=COMPANIES, filings=filings, facts=facts,
                        cutoff=kwargs.get('cutoff', CUTOFF), period_start=date(2025, 1, 1), code_revision='test')


class SecCoverageReportTests(unittest.TestCase):
    def test_zero_coverage_companies_and_concepts_are_explicit(self):
        result = report()
        self.assertEqual(result['summary']['company_count'], 2)
        self.assertEqual(result['summary']['companies_without_filings'], 1)
        self.assertEqual(result['summary']['companies_without_selected_facts'], 1)
        self.assertEqual(len(result['by_company_concept']), 2 * len(SELECTED_CONCEPTS))
        self.assertEqual(result['by_company'][1]['selected_concepts_present'], 0)

    def test_duplicate_versions_and_later_revisions_do_not_inflate_coverage(self):
        late = replace(FACT, observed_at=CUTOFF + timedelta(days=1), available_at=CUTOFF + timedelta(days=1), value=Decimal('999'))
        result = report(facts=[FACT, FACT, late])
        self.assertEqual(result['summary']['resolved_selected_fact_count'], 1)
        self.assertEqual(result['selected_fact_lineage_sha256'], report()['selected_fact_lineage_sha256'])

    def test_after_cutoff_filing_and_five_minute_buffer(self):
        self.assertEqual(report(cutoff=ACCEPTED + timedelta(minutes=4))['summary']['resolved_selected_fact_count'], 0)
        later_filing = replace(FILING, accepted_at=CUTOFF + timedelta(days=1))
        result = report(filings=[later_filing], facts=[])
        self.assertEqual(result['summary']['filing_count'], 0)

    def test_amendments_distinct_and_irrelevant_forms_excluded(self):
        amendment = replace(FILING, filing_id='f2', accession='a2', submitted_form='10-Q/A')
        amended_fact = replace(FACT, filing_fact_key='key2', filing_id='f2', accession_number='a2', submitted_form='10-Q/A', is_amendment=True)
        offering = replace(FILING, filing_id='bad', accession='bad', submitted_form='424B2')
        result = report(filings=[FILING, amendment, offering], facts=[FACT, amended_fact])
        self.assertEqual(result['summary']['filing_count'], 2)
        self.assertEqual(result['summary']['resolved_selected_fact_count'], 2)
        form = next(row for row in result['by_company_form'] if row['security_id'] == 'one' and row['canonical_form'] == '10-Q')
        self.assertEqual(form['amendment_count'], 1)
        self.assertEqual(form['submitted_forms'], {'10-Q': 1, '10-Q/A': 1})
        summary = next(row for row in result['accepted_form_coverage'] if row['canonical_form'] == '10-Q')
        self.assertEqual(summary, {'canonical_form': '10-Q', 'filing_count': 2,
                                   'companies_present': 1, 'amendment_count': 1})

    def test_8k_without_facts_is_counted_without_inventing_facts(self):
        result = report(filings=[replace(FILING, submitted_form='8-K', period_end=None)], facts=[])
        self.assertEqual(result['summary']['filing_count'], 1)
        form = next(row for row in result['by_company_form'] if row['security_id'] == 'one' and row['canonical_form'] == '8-K')
        self.assertEqual(form['without_reporting_period_count'], 1)

    def test_exact_ytd_and_quarter_periods_are_not_merged(self):
        ytd = replace(FACT, filing_fact_key='ytd', concept='NetIncomeLoss', period_start=date(2026, 1, 1))
        quarter = replace(ytd, filing_fact_key='quarter', period_start=date(2026, 4, 1))
        rows = report(facts=[ytd, quarter])['by_company_concept_form_period']
        self.assertEqual(len(rows), 2)
        self.assertEqual({row['period_start'] for row in rows}, {'2026-01-01', '2026-04-01'})

    def test_wrong_unit_and_period_window_excluded_and_null_not_imputed(self):
        old = replace(FACT, filing_fact_key='old', period_end=date(2024, 12, 31))
        other_unit = replace(FACT, filing_fact_key='unit', unit='EUR')
        result = report(facts=[old, other_unit])
        self.assertEqual(result['summary']['resolved_selected_fact_count'], 0)
        self.assertEqual(result['excluded_loaded_record_counts']['facts_outside_reporting_period_window'], 1)
        self.assertTrue(all(row['latest_period_end'] is None for row in result['by_company_concept']))

    def test_untrustworthy_availability_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'availability'):
            report(facts=[replace(FACT, available_at=ACCEPTED)])
        with self.assertRaisesRegex(ValueError, 'UTC offset'):
            report(cutoff=datetime(2026, 8, 2))

    def test_reports_deterministic_exclusive_and_hash_verified(self):
        result = report()
        self.assertEqual(result, report(facts=[FACT, FACT]))
        with TemporaryDirectory() as directory:
            output = Path(directory) / 'report'
            publish_report(result, output)
            manifest = json.loads((output / 'manifest.json').read_text())
            self.assertEqual(manifest['status'], 'completed')
            for name, digest in manifest['sha256'].items():
                self.assertEqual(sha256((output / name).read_bytes()).hexdigest(), digest)
            with self.assertRaises(FileExistsError):
                publish_report(result, output)


if __name__ == '__main__':
    unittest.main()
