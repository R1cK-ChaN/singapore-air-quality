import math
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from air_quality import REGIONS
from cards import prepare
from daily import wait_for_eleven


class DailyTests(unittest.TestCase):
    def test_waits_for_exact_hour_and_all_regions(self):
        day = date(2026, 9, 29)
        ready = {r: [42.0] * 24 for r in REGIONS}
        partial = {r: values.copy() for r, values in ready.items()}
        partial["north"][11] = math.nan  # Later readings cannot replace 11:00.
        with patch("daily.fetch") as fetch, patch("daily.read_grid", side_effect=[
                (day, partial), (day, ready)]), patch("daily.time.sleep") as sleep:
            wait_for_eleven(day, Path("unused"))
        self.assertEqual(fetch.call_count, 2)
        sleep.assert_called_once()

    def test_missing_eleven_cannot_produce_offline_or_timed_out_edition(self):
        day = date(2026, 9, 29)
        grid = {r: [42.0] * 11 + [math.nan] * 13 for r in REGIONS}
        for offline in (True, False):
            with self.subTest(offline=offline), patch("daily.fetch"), patch(
                    "daily.read_grid", return_value=(day, grid)), patch("daily.time.sleep") as sleep:
                with self.assertRaisesRegex(ValueError, "11:00 数据未齐"):
                    wait_for_eleven(day, Path("unused"), offline=offline, wait_minutes=0)
                sleep.assert_not_called()

    def test_refreshes_cached_partial_historical_day(self):
        day = date(2026, 9, 28)
        previous = day - timedelta(days=1)
        full = {r: [42.0] * 24 for r in REGIONS}
        partial = {r: [42.0] * 12 + [math.nan] * 12 for r in REGIONS}
        metadata = [{"name": r, "labelLocation": {"longitude": 103.8, "latitude": 1.35}}
                    for r in REGIONS]
        import json
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            for d in (previous, day):
                (output / d.isoformat()).mkdir()
                (output / d.isoformat() / "pm25.csv").touch()
            (output / day.isoformat() / "source.json").write_text(json.dumps(
                {"pages": [{"data": {"regionMetadata": metadata}}]}))
            with patch("cards.fetch") as fetch, patch("cards.read_grid", side_effect=[
                    (previous, partial), (previous, full), (day, full)]):
                _, summaries, _, _ = prepare(day, 2, output, False, cutoff_hour=11)
            fetch.assert_called_once_with(previous, output)
            self.assertEqual(summaries[0]["complete_hours"], 24)
            self.assertEqual(summaries[1]["last_hour"], 11)


if __name__ == "__main__":
    unittest.main()
