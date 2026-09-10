import unittest

from quantrade_research.secret_audit import scan_text


class SecretAuditTests(unittest.TestCase):
    def test_detects_credentials_without_returning_their_values(self) -> None:
        examples = {
            "config.env": "APCA_API_" + "SECRET_KEY=not-a-placeholder-value\n",
            "database.txt": "DATABASE_URL=postgresql://user:" + "actual-password@localhost/db\n",
            "key.txt": "-----BEGIN " + "PRIVATE KEY-----\nmaterial\n",
        }
        for path, content in examples.items():
            findings = scan_text(path, content)
            self.assertTrue(findings)
            self.assertNotIn(content.strip(), repr(findings))

    def test_allows_documented_and_ci_placeholders(self) -> None:
        content = "\n".join((
            "APCA_API_KEY_ID=replace-with-alpaca-key",
            "APCA_API_SECRET_KEY=ci-placeholder",
            "DATABASE_URL=postgresql://postgres:postgres@localhost/quantrade_ci",
        ))
        self.assertEqual(scan_text(".env.example", content), ())


if __name__ == "__main__":
    unittest.main()
