from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quantrade_research.demo_database import database_url_for, require_local_database, validate_demo_database_name


class DemoDatabaseSafetyTests(unittest.TestCase):
    def test_demo_database_name_requires_safe_suffix(self) -> None:
        self.assertEqual(validate_demo_database_name("quantrade_demo"), "quantrade_demo")
        for unsafe in ("quantdb", "quantrade-demo", "Quantrade_demo", "postgres;drop_demo"):
            with self.subTest(unsafe=unsafe), self.assertRaises(ValueError):
                validate_demo_database_name(unsafe)

    def test_database_url_replaces_only_database_path(self) -> None:
        actual = database_url_for(
            "postgresql://postgres:secret@localhost:5432/postgres?connect_timeout=5",
            "quantrade_demo",
        )
        self.assertEqual(
            actual,
            "postgresql://postgres:secret@localhost:5432/quantrade_demo?connect_timeout=5",
        )

    def test_demo_reset_rejects_remote_database(self) -> None:
        with self.assertRaisesRegex(ValueError, "local PostgreSQL"):
            require_local_database("postgresql://postgres:secret@example.com:5432/postgres")


if __name__ == "__main__":
    unittest.main()
