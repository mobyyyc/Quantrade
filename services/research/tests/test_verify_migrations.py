from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quantrade_research.verify_migrations import ordered_migrations, require_disposable_database


class MigrationVerificationTests(unittest.TestCase):
    def test_repository_migrations_are_contiguous_and_named_consistently(self) -> None:
        directory = Path(__file__).resolve().parents[1] / "db" / "migrations"
        migrations = ordered_migrations(directory)
        self.assertEqual(migrations[0].name, "0001_core_schema.sql")
        self.assertEqual(migrations[-1].name, "0036_add_decision_time_contracts.sql")
        self.assertEqual(len(migrations), 36)

    def test_gap_in_sequence_fails_before_database_access(self) -> None:
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "0001_first.sql").touch()
            (directory / "0003_third.sql").touch()
            with self.assertRaisesRegex(ValueError, "not contiguous"):
                ordered_migrations(directory)

    def test_only_explicit_ci_database_names_are_allowed(self) -> None:
        self.assertEqual(
            require_disposable_database("postgresql://runner:secret@localhost:5432/quantrade_ci"),
            "quantrade_ci",
        )
        with self.assertRaisesRegex(ValueError, "refuses database 'quantdb'"):
            require_disposable_database("postgresql://runner:secret@localhost:5432/quantdb")


if __name__ == "__main__":
    unittest.main()
