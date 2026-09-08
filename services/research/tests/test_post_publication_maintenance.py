from contextlib import ExitStack, contextmanager, redirect_stdout
from datetime import date, datetime
from io import StringIO
from unittest.mock import MagicMock, patch
import unittest

from quantrade_research import manual_daily_update as daily
from quantrade_research.paper_portfolio import publish_due_paper_portfolios, publish_paper_portfolio


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.day = date(2026, 9, 4)
        self.settings = MagicMock(database_url="unused")
        self.connection = MagicMock()

    def operations(self, stack):
        return [stack.enter_context(patch.object(daily, name)) for name in (
            "publish_due_paper_portfolios", "materialize_due_paper_portfolio_outcomes",
            "materialize_due_forward_score_outcomes", "materialize_forward_readiness_snapshot")]

    def test_failed_step_does_not_block_independent_steps_and_retry_completes(self):
        with ExitStack() as stack, redirect_stdout(StringIO()) as output:
            stack.enter_context(patch.object(daily, "_maintenance_completed", return_value=False))
            event = stack.enter_context(patch.object(daily, "_record_operation_event"))
            operations = self.operations(stack)
            operations[0].side_effect = RuntimeError("missing opening price")
            with self.assertRaises(SystemExit) as failed:
                daily._finish_maintenance(self.connection, self.settings, self.day)
            self.assertEqual(failed.exception.code, 2)
            self.assertEqual(event.call_args.args[2], "post_publication_warning")
            for operation in operations:
                operation.assert_called_once()
            self.assertIn("partial_completed", output.getvalue())
            operations[0].side_effect = None
            daily._finish_maintenance(self.connection, self.settings, self.day)
            self.assertEqual(event.call_args.args[2], "completed")
            self.assertEqual(event.call_args.kwargs["stage"], "portfolio")

    def test_completed_maintenance_is_noop(self):
        with ExitStack() as stack, redirect_stdout(StringIO()):
            stack.enter_context(patch.object(daily, "_maintenance_completed", return_value=True))
            operations = self.operations(stack)
            daily._finish_maintenance(self.connection, self.settings, self.day)
            for operation in operations:
                operation.assert_not_called()

    def test_failed_forward_outcomes_do_not_freeze_incomplete_readiness(self):
        with ExitStack() as stack, redirect_stdout(StringIO()):
            stack.enter_context(patch.object(daily, "_maintenance_completed", return_value=False))
            stack.enter_context(patch.object(daily, "_record_operation_event"))
            operations = self.operations(stack)
            operations[2].side_effect = RuntimeError("provider gap")
            with self.assertRaises(SystemExit):
                daily._finish_maintenance(self.connection, self.settings, self.day)
            operations[3].assert_not_called()

    def test_checkpoint_failure_is_partial_not_unqualified_success(self):
        with patch.object(daily, "_maintenance_completed", side_effect=RuntimeError("database down")), redirect_stdout(StringIO()) as output:
            with self.assertRaises(SystemExit) as failed:
                daily._finish_maintenance(self.connection, self.settings, self.day)
            self.assertEqual(failed.exception.code, 2)
            self.assertIn("partial_completed", output.getvalue())

    def test_completed_publication_retries_under_lock_without_ingestion_or_scoring(self):
        held = []
        @contextmanager
        def lock(_url):
            held.append(True)
            yield self.connection
            held.pop()
        def finish(*_args):
            self.assertEqual(held, [True])
        with ExitStack() as stack, redirect_stdout(StringIO()):
            stack.enter_context(patch("sys.argv", ["manual_daily_update"]))
            clock = stack.enter_context(patch.object(daily, "datetime"))
            clock.now.return_value = datetime(2026, 9, 4, 22, tzinfo=daily.TORONTO)
            stack.enter_context(patch.object(daily, "_settings", return_value=self.settings))
            stack.enter_context(patch.object(daily, "_symbols", return_value=["AAPL"]))
            stack.enter_context(patch.object(daily, "_ciks", return_value=[]))
            stack.enter_context(patch.object(daily.subprocess, "check_output", return_value="revision"))
            stack.enter_context(patch.object(daily, "_daily_update_lock", side_effect=lock))
            stack.enter_context(patch.object(daily, "_start_or_resume", return_value=(False, None)))
            maintenance = stack.enter_context(patch.object(daily, "_finish_maintenance", side_effect=finish))
            command = stack.enter_context(patch.object(daily, "_run"))
            scores = stack.enter_context(patch.object(daily, "_published_score_summary"))
            daily.main()
            maintenance.assert_called_once()
            command.assert_not_called()
            scores.assert_not_called()
        self.assertFalse(held)

    def test_candidate_filter_rejects_ordinary_days_and_missed_execution(self):
        for formation, next_open, execution, expected in (
            (date(2026, 9, 3), date(2026, 9, 4), date(2026, 9, 4), ()),
            (date(2026, 8, 31), date(2026, 9, 1), date(2026, 9, 4), ()),
            (date(2026, 8, 31), date(2026, 9, 1), date(2026, 9, 1), (date(2026, 8, 31),)),
        ):
            with patch("psycopg.connect") as connect, patch(
                "quantrade_research.paper_portfolio.publish_paper_portfolio", return_value=20
            ) as publish:
                cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
                cursor.fetchall.return_value = [(formation,)]
                cursor.fetchone.return_value = (next_open,)
                result = publish_due_paper_portfolios(settings=self.settings, execution_date=execution)
                self.assertEqual(result, expected)
                self.assertEqual(publish.call_count, len(expected))
                self.assertIn("date_trunc('month', session_date) <", cursor.execute.call_args_list[0].args[0])

    def test_existing_portfolio_returns_noop_under_transaction_lock(self):
        with patch("psycopg.connect") as connect:
            cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = (1,)
            self.assertEqual(publish_paper_portfolio(settings=self.settings, score_date=self.day), 0)
            self.assertIn("pg_advisory_xact_lock", cursor.execute.call_args_list[0].args[0])
            self.assertEqual(cursor.execute.call_count, 2)
