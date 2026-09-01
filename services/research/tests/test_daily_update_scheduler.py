from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class DailyUpdateSchedulerContractTests(unittest.TestCase):
    def test_installer_targets_the_canonical_script_with_safety_settings(self) -> None:
        installer = (REPOSITORY_ROOT / "scripts" / "install-daily-update-task.ps1").read_text(encoding="utf-8")
        for contract in (
            "run-daily-update.ps1",
            "Eastern Standard Time",
            "Monday, Tuesday, Wednesday, Thursday, Friday",
            "MultipleInstances IgnoreNew",
            "StartWhenAvailable",
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
            "windows_daily_update_task_v2",
            "run-daily-update.ps1",
            "LogonType",
            "RunLevel",
            "MultipleInstances",
            "RunOnlyIfNetworkAvailable",
            "StartWhenAvailable",
            "WakeToRun",
            "Hidden",
            "StartBoundary",
        ):
            self.assertIn(contract, verifier)


if __name__ == "__main__":
    unittest.main()
