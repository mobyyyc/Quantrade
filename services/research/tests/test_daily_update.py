import argparse
import unittest

from quantrade_research.ingest_filings import _ciks
from quantrade_research.manual_daily_update import _sec_network_environment


class DailyUpdateParsingTests(unittest.TestCase):
    def test_accepts_a_deduplicated_cik_list(self) -> None:
        self.assertEqual(_ciks("320193,0000320193,789019"), ["0000320193", "0000789019"])

    def test_rejects_an_empty_cik_list(self) -> None:
        with self.assertRaisesRegex(argparse.ArgumentTypeError, "valid CIK"):
            _ciks("not-a-cik")

    def test_sec_child_drops_only_proxy_configuration(self) -> None:
        environment = {
            "HTTP_PROXY": "http://127.0.0.1:8080", "HTTPS_PROXY": "http://127.0.0.1:8080",
            "ALL_PROXY": "http://127.0.0.1:8080", "DATABASE_URL": "postgresql://example",
            "SEC_USER_AGENT": "Quantrade contact@example.com",
        }
        result = _sec_network_environment(environment)
        self.assertNotIn("HTTP_PROXY", result)
        self.assertNotIn("HTTPS_PROXY", result)
        self.assertNotIn("ALL_PROXY", result)
        self.assertEqual(result["DATABASE_URL"], environment["DATABASE_URL"])
        self.assertEqual(result["SEC_USER_AGENT"], environment["SEC_USER_AGENT"])
