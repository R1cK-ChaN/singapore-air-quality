import csv
import math
import tempfile
import unittest
from datetime import date
from pathlib import Path

from air_quality import fetch_pages, normalize, read_grid


class AirQualityTests(unittest.TestCase):
    def item(self, timestamp, value, updated=None):
        return {"timestamp": timestamp, "updatedTimestamp": updated or timestamp,
                "readings": {"pm25_one_hourly": {"central": value}}}

    def test_pagination_and_repeated_token(self):
        calls = []
        pages = [{"code": 0, "data": {"items": [], "paginationToken": "next"}},
                 {"code": 0, "data": {"items": []}}]
        def get(url):
            calls.append(url)
            return pages[len(calls) - 1]
        self.assertEqual(len(fetch_pages(date(2026, 9, 28), get)), 2)
        self.assertIn("paginationToken=next", calls[1])
        with self.assertRaisesRegex(ValueError, "重复"):
            fetch_pages(date(2026, 9, 28), lambda url: pages[0])

    def test_sgt_filter_revision_and_missing_region(self):
        items = [self.item("2026-09-27T16:00:00+00:00", 20),
                 self.item("2026-09-28T00:00:00+08:00", 25, "2026-09-28T01:00:00+08:00"),
                 self.item("2026-09-27T23:00:00+08:00", 99)]
        rows = normalize([{"data": {"items": items}}], date(2026, 9, 28))
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[-1]["pm25_ug_m3"], 25)
        self.assertEqual(rows[0]["pm25_ug_m3"], "")
        self.assertEqual(rows[-1]["timestamp_sgt"], "2026-09-28T00:00:00+08:00")

    def test_csv_gap_stays_missing_and_duplicate_fails(self):
        items = [self.item("2026-09-28T00:00:00+08:00", 0),
                 self.item("2026-09-28T02:00:00+08:00", 60)]
        rows = normalize([{"data": {"items": items}}], date(2026, 9, 28))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data.csv"
            def save(records):
                with path.open("w", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=rows[0])
                    writer.writeheader()
                    writer.writerows(records)
            save(rows)
            _, grid = read_grid(path)
            self.assertEqual(grid["central"][0], 0)
            self.assertTrue(math.isnan(grid["central"][1]))
            self.assertEqual(grid["central"][2], 60)
            save(rows + rows[:1])
            with self.assertRaisesRegex(ValueError, "重复"):
                read_grid(path)

    def test_invalid_and_empty_data_rejected(self):
        for value in [-1, float("inf"), "nan"]:
            with self.assertRaises(ValueError):
                normalize([{"data": {"items": [self.item("2026-09-28T00:00:00+08:00", value)]}}], date(2026, 9, 28))
        with self.assertRaisesRegex(ValueError, "没有"):
            normalize([{"data": {"items": []}}], date(2026, 9, 28))


if __name__ == "__main__":
    unittest.main()
