from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class DailyUpdateEntrypointContractTests(unittest.TestCase):
    def test_powershell_script_is_the_only_python_launch_boundary(self) -> None:
        script = (REPOSITORY_ROOT / "scripts" / "run-daily-update.ps1").read_text(encoding="utf-8")
        route = (
            REPOSITORY_ROOT
            / "apps"
            / "web"
            / "src"
            / "app"
            / "api"
            / "v1"
            / "operations"
            / "daily-update"
            / "route.ts"
        ).read_text(encoding="utf-8")

        self.assertEqual(script.count('"quantrade_research.manual_daily_update"'), 1)
        self.assertIn('contract = "canonical_daily_update_v1"', script)
        self.assertIn("run-daily-update.ps1", (
            REPOSITORY_ROOT
            / "apps"
            / "web"
            / "src"
            / "lib"
            / "daily-update-launcher.ts"
        ).read_text(encoding="utf-8"))
        self.assertNotIn("quantrade_research.manual_daily_update", route)
        self.assertIn("dailyUpdateLaunchSpec", route)

    def test_script_description_has_one_resolved_execution_contract(self) -> None:
        script = (REPOSITORY_ROOT / "scripts" / "run-daily-update.ps1").read_text(encoding="utf-8")
        for field in (
            "workspaceRoot",
            "envFile",
            "workingDirectory",
            "pythonPath",
            "executable",
            "arguments",
        ):
            self.assertIn(field, script)

    def test_provider_retries_keep_incremental_idempotency_flags(self) -> None:
        orchestrator = (
            REPOSITORY_ROOT
            / "services"
            / "research"
            / "src"
            / "quantrade_research"
            / "manual_daily_update.py"
        ).read_text(encoding="utf-8")

        self.assertEqual(orchestrator.count("retry_policy=_PROVIDER_RETRY_POLICY"), 3)
        self.assertGreaterEqual(orchestrator.count('"--only-missing"'), 2)
        self.assertIn('"--incremental"', orchestrator)
        self.assertIn("with _daily_update_lock", orchestrator)


if __name__ == "__main__":
    unittest.main()
