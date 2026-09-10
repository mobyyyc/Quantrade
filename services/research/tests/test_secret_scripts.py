from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class SecretScriptTests(unittest.TestCase):
    def test_local_acl_script_is_exact_path_and_fail_closed(self) -> None:
        script = (ROOT / "scripts" / "protect-local-secrets.ps1").read_text(encoding="utf-8")
        self.assertIn("exact .env file", script)
        self.assertIn("SetAccessRuleProtection($true, $false)", script)
        self.assertIn("BroadAccessRules", script)

    def test_database_rotation_uses_crypto_and_never_prints_the_password(self) -> None:
        script = (ROOT / "scripts" / "rotate-local-postgresql-password.ps1").read_text(encoding="utf-8")
        self.assertIn("RandomNumberGenerator", script)
        self.assertIn("RedirectStandardInput", script)
        self.assertNotIn("Write-Output $newPassword", script)
        self.assertNotIn("Write-Host $newPassword", script)
        self.assertIn("protect-local-secrets.ps1", script)


if __name__ == "__main__":
    unittest.main()
