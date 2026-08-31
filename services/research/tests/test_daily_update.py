import argparse
from contextlib import redirect_stdout
from datetime import date
from io import StringIO
import json
import subprocess
import unittest

from quantrade_research.ingest_filings import _ciks
from quantrade_research.manual_daily_update import (
    RetryPolicy, _is_transient_provider_failure, _progress, _run, _sec_network_environment,
)


class DailyUpdateParsingTests(unittest.TestCase):
    def test_retries_a_transient_provider_failure_with_the_identical_command(self) -> None:
        calls: list[list[str]] = []

        def runner(command, **_kwargs):
            calls.append(list(command))
            if len(calls) == 1:
                raise subprocess.CalledProcessError(
                    1, command, stderr="Alpaca returned HTTP 503: temporarily unavailable",
                )
            return subprocess.CompletedProcess(command, 0, stdout="ingested=1\n", stderr="")

        pauses: list[float] = []
        retries: list[tuple[int, int, float]] = []
        result = _run(
            ["python", "-m", "provider_ingestion", "--only-missing"], {}, operation="market-data ingestion",
            retry_policy=RetryPolicy(attempts=3, base_delay_seconds=0.25, maximum_delay_seconds=1),
            on_retry=lambda attempt, total, delay: retries.append((attempt, total, delay)),
            runner=runner, sleep=pauses.append,
        )

        self.assertEqual(result, "ingested=1")
        self.assertEqual(calls, [calls[0], calls[0]])
        self.assertEqual(pauses, [0.25])
        self.assertEqual(retries, [(2, 3, 0.25)])

    def test_does_not_retry_permanent_provider_or_validation_failures(self) -> None:
        for detail in (
            "Alpaca returned HTTP 401: unauthorized",
            "SEC daily filing index for 2026-08-31 has not been published yet",
            "ValueError: invalid response payload",
        ):
            calls = 0

            def runner(command, **_kwargs):
                nonlocal calls
                calls += 1
                raise subprocess.CalledProcessError(1, command, stderr=detail)

            with self.assertRaisesRegex(RuntimeError, "provider ingestion failed"):
                _run(
                    ["python", "provider_ingestion.py"], {}, operation="provider ingestion",
                    retry_policy=RetryPolicy(attempts=3, base_delay_seconds=0),
                    runner=runner, sleep=lambda _seconds: None,
                )
            self.assertEqual(calls, 1)

    def test_transient_provider_failure_stops_after_the_bound(self) -> None:
        calls = 0

        def runner(command, **_kwargs):
            nonlocal calls
            calls += 1
            raise subprocess.CalledProcessError(1, command, stderr="SEC returned HTTP 429")

        with self.assertRaisesRegex(RuntimeError, "after 3 attempts"):
            _run(
                ["python", "provider_ingestion.py"], {}, operation="SEC filing ingestion",
                retry_policy=RetryPolicy(attempts=3, base_delay_seconds=0),
                runner=runner, sleep=lambda _seconds: None,
            )
        self.assertEqual(calls, 3)

    def test_transient_failure_classifier_is_narrow(self) -> None:
        self.assertTrue(_is_transient_provider_failure("HTTP 504 gateway timeout"))
        self.assertTrue(_is_transient_provider_failure("urlopen error: connection reset by peer"))
        self.assertFalse(_is_transient_provider_failure("HTTP 403 forbidden"))
        self.assertFalse(_is_transient_provider_failure("has not been published yet; retry after 10 p.m."))

    def test_progress_is_a_versioned_single_line_json_contract(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            _progress("market_data", "started", "Fetching missing bars.", score_date=date(2026, 8, 31))
        line = output.getvalue().strip()
        self.assertTrue(line.startswith("QUANTRADE_PROGRESS "))
        payload = json.loads(line.removeprefix("QUANTRADE_PROGRESS "))
        self.assertEqual(payload, {
            "contract": "daily_update_progress_v1",
            "message": "Fetching missing bars.",
            "scoreDate": "2026-08-31",
            "stage": "market_data",
            "status": "started",
        })

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
