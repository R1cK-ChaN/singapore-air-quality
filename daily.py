#!/usr/bin/env python3
"""Daily 11:00 SGT edition: fetch, render the approved two cards, verify, record."""
from __future__ import annotations

import argparse
import json
import math
import time
from datetime import date, datetime
from pathlib import Path

from air_quality import DEFAULT_OUTPUT, REGIONS, SGT, fetch, read_grid
from cards import limit_grid, render, summarize


def wait_for_eleven(day, output, offline=False, wait_minutes=60):
    """Require all five observations at exactly 11:00 before rendering."""
    deadline = time.monotonic() + wait_minutes * 60
    while True:
        if not offline:
            fetch(day, output)
        csv_day, grid = read_grid(output / day.isoformat() / "pm25.csv")
        if csv_day != day:
            raise ValueError("CSV 日期与出图日期不一致")
        missing = [REGIONS[r] for r in REGIONS if not math.isfinite(grid[r][11])]
        if not missing:
            return
        remaining = deadline - time.monotonic()
        if offline or remaining <= 0:
            raise ValueError(f"{day} 11:00 数据未齐：{'、'.join(missing)}；未生成图片")
        print(f"等待 {day} 11:00 数据：{'、'.join(missing)}", flush=True)
        time.sleep(min(60, remaining))


def run_daily(day, output=DEFAULT_OUTPUT, offline=False, wait_minutes=60):
    from PIL import Image

    output = Path(output).resolve()
    started = datetime.now(SGT)
    folder = output / day.isoformat() / "cards"
    folder.mkdir(parents=True, exist_ok=True)
    report_path = folder / "daily_run.json"
    report = {"date": day.isoformat(), "timezone": "Asia/Singapore", "cutoff_hour": 11,
              "started_at": started.isoformat(), "status": "running", "offline": offline}
    def record():
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    record()
    try:
        wait_for_eleven(day, output, offline, wait_minutes)
        render(day, days=7, output=output, offline=offline, cutoff_hour=11)
        _, grid = read_grid(output / day.isoformat() / "pm25.csv")
        grid = limit_grid(grid, 11)
        actual_hour = summarize(day, grid)["last_hour"]
        missing = [r for r in REGIONS if not math.isfinite(grid[r][actual_hour])]
        if actual_hour != 11 or missing:
            raise ValueError("11:00 数据校验失败")
        # Data absent from the latest hour are never replaced with older observations.
        paths = []
        for name in ("01-island-overview", "02-regional-comparison"):
            png, svg = folder / f"{name}.png", folder / f"{name}.svg"
            with Image.open(png) as picture:
                picture.load()
                if picture.size != (1080, 1440) or picture.convert("RGB").getpixel((0, 0)) != (255, 255, 255):
                    raise ValueError(f"尺寸或纯白底色校验失败：{png.name}")
            if not svg.is_file() or svg.stat().st_size == 0:
                raise ValueError(f"SVG 缺失：{svg.name}")
            paths.append(str(png))
        report.update(status="complete", actual_hour=actual_hour, data_lag_hours=11 - actual_hour,
                      missing_regions=missing, images=paths,
                      completed_at=datetime.now(SGT).isoformat())
        record()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return report
    except Exception as exc:
        report.update(status="failed", error=str(exc), completed_at=datetime.now(SGT).isoformat())
        record()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, default=datetime.now(SGT).date())
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--offline", action="store_true", help="仅使用缓存重跑，供历史复现与校验")
    parser.add_argument("--wait-minutes", type=int, default=60, help="等待五区11:00读数的最长分钟数，默认60")
    args = parser.parse_args()
    if args.wait_minutes < 0:
        parser.error("--wait-minutes 不能为负数")
    try:
        run_daily(args.date, args.out_dir, args.offline, args.wait_minutes)
    except (ValueError, KeyError, OSError, RuntimeError, ImportError) as exc:
        parser.exit(1, f"每日出图失败：{exc}\n")


if __name__ == "__main__":
    main()
