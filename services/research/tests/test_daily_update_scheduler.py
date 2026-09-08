from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class DailyUpdateSchedulerContractTests(unittest.TestCase):
    def test_installer_targets_the_canonical_script_with_safety_settings(self) -> None:
        installer = (REPOSITORY_ROOT / "scripts" / "install-daily-update-task.ps1").read_text(encoding="utf-8")
        for contract in (
            "run-daily-update-scheduled.ps1",
            "Eastern Standard Time",
            "Monday, Tuesday, Wednesday, Thursday, Friday",
            "MultipleInstances IgnoreNew",
            "StartWhenAvailable",
            "AtLogOn",
            "RunOnlyIfNetworkAvailable",
            "RestartCount 2",
            "LogonType Interactive",
            "currentUserSid",
            "registeredUserSid",
            '"-WindowStyle Hidden"',
            "-Hidden",
        ):
            self.assertIn(contract, installer)
        self.assertNotIn("quantrade_research.manual_daily_update", installer)

    def test_uninstaller_is_explicit_and_scoped_to_one_task(self) -> None:
        uninstaller = (REPOSITORY_ROOT / "scripts" / "uninstall-daily-update-task.ps1").read_text(encoding="utf-8")
        self.assertIn('[string]$TaskName = "Quantrade Daily Update"', uninstaller)
        self.assertIn("Unregister-ScheduledTask -TaskName $TaskName", uninstaller)
        self.assertNotIn("Get-ScheduledTask |", uninstaller)

    def test_verifier_checks_the_installed_contract(self) -> None:
        verifier = (REPOSITORY_ROOT / "scripts" / "verify-daily-update-task.ps1").read_text(encoding="utf-8")
        for contract in (
            "windows_daily_update_task_v3",
            "run-daily-update-scheduled.ps1",
            "LogonType",
            "RunLevel",
            "MultipleInstances",
            "RunOnlyIfNetworkAvailable",
            "StartWhenAvailable",
            "WakeToRun",
            "Hidden",
            "StartBoundary",
            "LogonCatchUp",
        ):
            self.assertIn(contract, verifier)

    def test_scheduled_wrapper_is_hidden_window_safe_and_time_guarded(self) -> None:
        wrapper = (REPOSITORY_ROOT / "scripts" / "run-daily-update-scheduled.ps1").read_text(encoding="utf-8")
        self.assertIn('Join-Path $workspaceRoot "scripts\\run-daily-update.ps1"', wrapper)
        self.assertIn('$isDue = $isWeekday -and $now.TimeOfDay -ge $scheduledTime', wrapper)
        self.assertIn('daily-update-scheduler.log', wrapper)
        self.assertIn('exit $exitCode', wrapper)

    def test_operations_installer_applies_and_verifies_both_approved_times(self) -> None:
        installer = (REPOSITORY_ROOT / "scripts" / "install-operations-schedule.ps1").read_text(encoding="utf-8")
        self.assertIn('[string]$BackupAt = "21:45"', installer)
        self.assertIn('[string]$DailyUpdateAt = "22:15"', installer)
        self.assertIn('install-postgresql-backup-task.ps1', installer)
        self.assertIn('install-daily-update-task.ps1', installer)
        self.assertIn('verify-postgresql-backup-task.ps1', installer)
        self.assertIn('verify-daily-update-task.ps1', installer)


if __name__ == "__main__":
    unittest.main()
