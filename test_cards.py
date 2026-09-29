import math
import unittest
from datetime import date

from air_quality import REGIONS
from cards import band, colored_segments, limit_grid, project, rolling_window, summarize


class CardDataTests(unittest.TestCase):
    def test_daily_cutoff_excludes_later_readings_without_relabeling(self):
        grid = {r: list(range(24)) for r in REGIONS}
        limited = limit_grid(grid, 11)
        result = summarize(date(2026, 9, 29), limited)
        self.assertEqual(result["last_hour"], 11)
        self.assertEqual(result["complete_hours"], 12)
        self.assertEqual(result["partial_mean_ug_m3"], 5.5)
        self.assertTrue(math.isnan(limited["north"][12]))
        self.assertEqual(grid["north"][12], 12)
        for r in REGIONS:
            limited[r][11] = math.nan
        self.assertEqual(summarize(date(2026, 9, 29), limited)["last_hour"], 10)

    def test_rolling_window_includes_both_endpoints_and_midnight(self):
        previous = {r: list(range(24)) for r in REGIONS}
        current = {r: list(range(100, 124)) for r in REGIONS}
        for hour in [0, 11, 23]:
            times, series = rolling_window(date(2026, 10, 1), hour, previous, current)
            self.assertEqual(len(times), 25)
            self.assertEqual(times[0].date(), date(2026, 9, 30))
            self.assertEqual(times[-1].date(), date(2026, 10, 1))
            self.assertEqual(times[0].hour, hour)
            self.assertEqual(times[-1].hour, hour)
            self.assertEqual((times[-1] - times[0]).total_seconds(), 24 * 3600)
            self.assertEqual(series["north"], list(range(hour, 24)) + list(range(100, 101 + hour)))
        previous["north"][23] = math.nan
        _, series = rolling_window(date(2026, 10, 1), 11, previous, current)
        self.assertTrue(math.isnan(series["north"][12]))
        self.assertEqual(series["north"][13], 100)

    def test_daily_mean_weights_five_regions_equally(self):
        grid = {r: [float(i * 10)] * 24 for i, r in enumerate(REGIONS)}
        row = summarize(date(2026, 9, 28), grid)
        self.assertEqual(row["daily_mean_ug_m3"], 20)
        self.assertEqual(row["complete_hours"], 24)
        self.assertTrue(math.isnan(row["partial_mean_ug_m3"]))

    def test_partial_day_is_not_reported_as_daily_mean(self):
        grid = {r: [10, 30] + [math.nan] * 22 for r in REGIONS}
        row = summarize(date(2026, 9, 29), grid)
        self.assertTrue(math.isnan(row["daily_mean_ug_m3"]))
        self.assertEqual(row["partial_mean_ug_m3"], 20)
        self.assertEqual(row["last_hour"], 1)
        grid["north"][0] = math.nan
        # Missing one region/hour must not be silently averaged away.
        row = summarize(date(2026, 9, 29), grid)
        self.assertTrue(math.isnan(row["daily_mean_ug_m3"]))
        self.assertTrue(math.isnan(row["partial_mean_ug_m3"]))

    def test_mercator_orientation_and_known_origin(self):
        self.assertEqual(project(0, 0, zoom=0), (128, 128))
        x, y = project(103.82, 1.35)
        self.assertGreater(project(103.94, 1.35)[0], x)
        self.assertLess(project(103.82, 1.42)[1], y)

    def test_band_boundaries(self):
        self.assertEqual([band(v)[0] for v in [55, 56, 150, 151, 250, 251]],
                         ["正常", "升高", "升高", "高", "高", "很高"])
        self.assertEqual(band(math.nan)[0], "缺测")
        self.assertEqual(band(55.01)[0], "升高")
        self.assertEqual(band(150.01)[0], "高")
        self.assertEqual(band(250.01)[0], "很高")

    def test_connectors_change_color_at_crossings_and_preserve_gaps(self):
        green, amber, red = [band(v)[1] for v in (55, 56, 151)]
        segments, colors = colored_segments([40, 160])
        self.assertEqual(colors, [green, amber, red])
        self.assertEqual(segments[0][-1][1], 55)
        self.assertEqual(segments[1][-1][1], 150)
        self.assertEqual(colored_segments([160, 40])[1], [red, amber, green])
        self.assertEqual(colored_segments([40, math.nan, 160]), ([], []))
        self.assertEqual(colored_segments([55, 55])[1], [green])


if __name__ == "__main__":
    unittest.main()
