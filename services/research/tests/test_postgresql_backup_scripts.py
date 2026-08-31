from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPOSITORY_ROOT / "scripts"


class PostgreSqlBackupScriptContractTests(unittest.TestCase):
    def test_backup_is_atomic_verified_and_retention_bounded(self) -> None:
        script = (SCRIPTS / "backup-postgresql.ps1").read_text(encoding="utf-8")
        self.assertIn('"--format=custom"', script)
        self.assertIn('"--compress=6"', script)
        self.assertIn('"$backupPath.partial"', script)
        self.assertIn("Test-QuantradeBackupArchive", script)
        self.assertIn("Get-FileHash", script)
        self.assertIn("$MinimumBackups", script)
        self.assertIn("$RetentionDays", script)
        self.assertIn('contract = "quantrade_postgresql_backup_v1"', script)

    def test_password_is_passed_through_environment_not_command_arguments(self) -> None:
        common = (SCRIPTS / "postgres-backup-common.ps1").read_text(encoding="utf-8")
        self.assertIn("$env:PGPASSWORD = $Password", common)
        self.assertNotIn("--password=", common)
        self.assertIn("Remove-Item Env:PGPASSWORD", common)

    def test_restore_drill_uses_an_isolated_database_and_always_removes_it(self) -> None:
        script = (SCRIPTS / "test-postgresql-restore.ps1").read_text(encoding="utf-8")
        self.assertIn('"quantrade_restore_drill_', script)
        self.assertIn('"--exit-on-error"', script)
        self.assertIn("information_schema.tables", script)
        self.assertIn("finally", script)
        self.assertIn('Get-QuantradePostgresTool -Name "dropdb"', script)
        self.assertIn('if (-not $testDatabase.StartsWith("quantrade_restore_drill_"))', script)

    def test_scheduler_invokes_the_canonical_backup_script(self) -> None:
        installer = (SCRIPTS / "install-postgresql-backup-task.ps1").read_text(encoding="utf-8")
        verifier = (SCRIPTS / "verify-postgresql-backup-task.ps1").read_text(encoding="utf-8")
        for content in (installer, verifier):
            self.assertIn("backup-postgresql.ps1", content)
            self.assertIn("windows_postgresql_backup_task_v1", content)
            self.assertIn("CodexRequired = $false", content)
            self.assertIn("WebAppRequired = $false", content)
        self.assertIn("New-ScheduledTaskTrigger -Daily", installer)
        self.assertIn("-MultipleInstances IgnoreNew", installer)

    def test_backup_directory_is_git_ignored(self) -> None:
        gitignore = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("data/backups/", gitignore)


if __name__ == "__main__":
    unittest.main()
