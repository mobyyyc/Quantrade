from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quantrade_research.database_storage_monitor import (
    RelationSize, build_report, latest_verified_report, load_verified_report, publish,
)


NOW = datetime(2026, 9, 3, tzinfo=timezone.utc)


def relation(name='facts', size=1024**3):
    return RelationSize('quantrade', name, size, size // 2, size // 3, size - size // 2 - size // 3, 100)


def report(size=10 * 1024**3, relations=None, baseline=None):
    return build_report(database='quantdb', database_bytes=size, relations=relations or [relation()],
                        captured_at=NOW, code_revision='test', baseline=baseline)


class DatabaseStorageMonitorTests(unittest.TestCase):
    def test_first_snapshot_is_baseline(self):
        result = report()
        self.assertEqual(result['status'], 'baseline')
        self.assertIsNone(result['database_delta_bytes'])
        self.assertEqual(result['relations'][0]['comparison_status'], 'baseline')

    def test_threshold_requires_absolute_and_relative_growth(self):
        baseline = report()
        current = report(size=baseline['database_bytes'], relations=[relation(size=1124 * 1024**2)], baseline=baseline)
        self.assertEqual(current['status'], 'normal')
        warning = report(size=baseline['database_bytes'], relations=[relation(size=1280 * 1024**2)], baseline=baseline)
        self.assertEqual(warning['status'], 'warning')

    def test_critical_database_growth_has_precedence(self):
        baseline = report()
        result = report(size=13 * 1024**3, baseline=baseline)
        self.assertEqual(result['status'], 'critical')
        self.assertEqual(result['findings'][0]['scope'], 'database')

    def test_new_and_removed_relations_are_not_growth_warnings(self):
        baseline = report(relations=[relation('old')])
        result = report(relations=[relation('new')], baseline=baseline)
        self.assertEqual(result['status'], 'normal')
        self.assertEqual(result['relations'][0]['comparison_status'], 'new')
        self.assertEqual(result['findings'][0]['severity'], 'information')

    def test_rejects_invalid_observations(self):
        with self.assertRaisesRegex(ValueError, 'UTC offset'):
            build_report(database='q', database_bytes=1, relations=[], captured_at=datetime(2026, 1, 1), code_revision='x')
        with self.assertRaisesRegex(ValueError, 'negative'):
            report(size=-1)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            report(relations=[relation(), relation()])

    def test_published_reports_are_immutable_verified_baselines(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / '001'
            publish(report(), first)
            path, loaded = latest_verified_report(root)
            self.assertEqual(path, first)
            self.assertEqual(loaded['database_bytes'], 10 * 1024**3)
            with self.assertRaises(FileExistsError):
                publish(report(), first)
            data = json.loads((first / 'manifest.json').read_text())
            data['sha256']['storage.json'] = '0' * 64
            (first / 'manifest.json').write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'checksum'):
                load_verified_report(first)


if __name__ == '__main__':
    unittest.main()
