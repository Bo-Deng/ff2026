"""Verify rendered methodology keeps completed, forecast and future weeks distinct."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class BuildWeekLabels(unittest.TestCase):
    def test_week_advancement_does_not_replace_inserted_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for directory in ('scripts', 'data', 'content'):
                shutil.copytree(ROOT / directory, root / directory)
            for completed in (9, 10, 11):
                with self.subTest(completed=completed):
                    path = root / 'data/dashboard.json'
                    dashboard = json.loads(path.read_text())
                    dashboard.update(completed_week=completed, next_week=completed+1)
                    path.write_text(json.dumps(dashboard))
                    subprocess.run([sys.executable, str(root/'scripts/build_site.py')], check=True, capture_output=True)
                    page = (root/'docs/methodology.html').read_text()
                    self.assertIn(f'frozen snapshot after Week {completed}.', page)
                    self.assertIn(f'draw weekly team scores for Weeks {completed+1}–17.', page)
                    self.assertIn(f'Weeks {completed+1}–14 follow the actual league schedule', page)
                    self.assertIn(f'Weeks {completed+2}–17 use each week', page)
                    self.assertIn(f'Weeks 1–{completed} history', page)
                    self.assertIn('Beginning with Week 10, report charts', page)

if __name__ == '__main__':
    unittest.main()
