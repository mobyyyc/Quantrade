import argparse
import unittest

from quantrade_research.ingest_filings import _ciks


class DailyUpdateParsingTests(unittest.TestCase):
    def test_accepts_a_deduplicated_cik_list(self) -> None:
        self.assertEqual(_ciks("320193,0000320193,789019"), ["0000320193", "0000789019"])

    def test_rejects_an_empty_cik_list(self) -> None:
        with self.assertRaisesRegex(argparse.ArgumentTypeError, "valid CIK"):
            _ciks("not-a-cik")
