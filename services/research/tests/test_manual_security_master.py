from datetime import date
from pathlib import Path
import sys
import unittest


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from quantrade_research.ingest_manual_security_master import (
    ManualSecurityMasterInputError,
    parse_manual_security_master_csv,
)


class ManualSecurityMasterTests(unittest.TestCase):
    def test_parses_an_explicit_manual_fallback_with_supported_exchange(self) -> None:
        rows = parse_manual_security_master_csv(
            b"ticker,issuer_name,cik,exchange,source\nCBOE,Cboe Global Markets,0001374310,Cboe BZX,https://example.test\n",
            date(2026, 8, 21),
        )
        self.assertEqual(rows[0].ticker, "CBOE")
        self.assertEqual(rows[0].exchange_mic, "BATS")

    def test_rejects_a_fallback_without_source_lineage(self) -> None:
        with self.assertRaises(ManualSecurityMasterInputError):
            parse_manual_security_master_csv(
                b"ticker,issuer_name,cik,exchange,source\nCBOE,Cboe Global Markets,0001374310,Cboe BZX,\n",
                date(2026, 8, 21),
            )


if __name__ == "__main__":
    unittest.main()
