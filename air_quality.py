#!/usr/bin/env python3
"""Fetch NEA hourly PM2.5, persist source data, and plot the saved CSV."""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

SGT = ZoneInfo("Asia/Singapore")
API = "https://api-open.data.gov.sg/v2/real-time/api/pm25"
REGIONS = {"north": "北区", "south": "南区", "east": "东区", "west": "西区", "central": "中区"}
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "output"


def request_json(url: str) -> dict:
    headers = {"User-Agent": "SG-Air-Notes/1.0", "Accept": "application/json"}
    if os.environ.get("DATA_GOV_SG_API_KEY"):
        headers["x-api-key"] = os.environ["DATA_GOV_SG_API_KEY"]
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers=headers), timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            if attempt == 2 or (exc.code != 429 and exc.code < 500):
                raise RuntimeError(f"官方接口返回 HTTP {exc.code}") from None
        except (URLError, TimeoutError):
            if attempt == 2:
                raise RuntimeError("官方接口连接失败，请稍后重试") from None
        time.sleep(2 ** (attempt + 1))
    raise RuntimeError("未取得数据")


def fetch_pages(day: date, get=request_json) -> list[dict]:
    pages, seen_tokens = [], set()
    params = {"date": day.isoformat()}
    while True:
        page = get(API + "?" + urlencode(params))
        if page.get("code") != 0 or not isinstance(page.get("data"), dict):
            raise ValueError("官方接口未返回成功数据")
        pages.append(page)
        token = page["data"].get("paginationToken")
        if not token:
            return pages
        if token in seen_tokens:
            raise ValueError("接口分页 token 重复，停止抓取")
        seen_tokens.add(token)
        params["paginationToken"] = token


def parse_timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("数据时间缺少时区")
    return result.astimezone(SGT)


def concentration(value) -> float:
    if value is None or value == "":
        return math.nan
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError("PM2.5 必须为非负有限数值，缺测请留空")
    return result


def normalize(pages: list[dict], day: date) -> list[dict]:
    # Keep the latest revision if a timestamp appears on multiple pages.
    by_time = {}
    for page in pages:
        for item in page["data"]["items"]:
            stamp = parse_timestamp(item["timestamp"])
            if stamp.date() != day:
                continue
            if stamp.minute or stamp.second or stamp.microsecond:
                raise ValueError("收到非整点读数，请检查官方数据格式")
            updated = parse_timestamp(item.get("updatedTimestamp", item["timestamp"]))
            old = by_time.get(stamp)
            if old is None or updated >= old[0]:
                by_time[stamp] = (updated, item["readings"]["pm25_one_hourly"])
    if not by_time:
        raise ValueError(f"{day} 没有可用读数")
    rows = []
    for stamp, (updated, values) in sorted(by_time.items()):
        for region in REGIONS:
            value = concentration(values.get(region))
            rows.append({"timestamp_sgt": stamp.isoformat(), "region": region,
                         "pm25_ug_m3": "" if math.isnan(value) else value,
                         "updated_timestamp_sgt": updated.isoformat()})
    return rows


def fetch(day: date, output: Path) -> Path:
    if day > datetime.now(SGT).date():
        raise ValueError("不能抓取未来日期")
    folder = output / day.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    pages = fetch_pages(day)
    raw = {"source": API, "date": day.isoformat(), "timezone": "Asia/Singapore",
           "retrieved_at": datetime.now(SGT).isoformat(), "pages": pages}
    (folder / "source.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = normalize(pages, day)
    path = folder / "pm25.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"数据已保存：{path}（{len(rows)} 条区域记录）")
    return path


def read_grid(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("CSV 没有数据")
    day = parse_timestamp(rows[0]["timestamp_sgt"]).date()
    grid = {region: [math.nan] * 24 for region in REGIONS}
    seen = set()
    for row in rows:
        stamp = parse_timestamp(row["timestamp_sgt"])
        region = row["region"]
        if stamp.date() != day or stamp.minute or stamp.second or stamp.microsecond or region not in REGIONS:
            raise ValueError("CSV 必须为同一天、五区内的逐小时读数")
        key = (stamp.hour, region)
        if key in seen:
            raise ValueError("CSV 存在重复的时间和区域")
        seen.add(key)
        grid[region][stamp.hour] = concentration(row["pm25_ug_m3"])
    if not any(math.isfinite(v) for values in grid.values() for v in values):
        raise ValueError("CSV 没有有效浓度")
    return day, grid


def plot(path: Path, output: Path | None = None, font: Path | None = None):
    # Import only for plotting: fetching needs no third-party packages.
    from typography import configure_font
    configure_font(font, size=11)
    import matplotlib.pyplot as plt

    day, grid = read_grid(path)
    ink, teal, orange = "#193D3E", "#117F80", "#B76232"
    observations = [(v, hour, region) for region, values in grid.items()
                    for hour, v in enumerate(values) if math.isfinite(v)]
    peak = max(value for value, _, _ in observations)
    peak_points = [(hour, region) for value, hour, region in observations if value == peak]
    count = len(observations)
    last_hour = max(hour for _, hour, _ in observations)
    complete = count == 120
    coverage = "全天回顾" if complete else f"不完整数据 · 最后读数 {last_hour:02}:00"
    # A shared fixed baseline supports daily comparisons; expand without clipping.
    ymax = max(160, math.ceil(peak / 50) * 50)
    fig, axes = plt.subplots(5, 1, figsize=(10.8, 14.4), dpi=100, sharex=True, sharey=True)
    fig.set_facecolor("#F6F4EE")
    fig.subplots_adjust(left=.11, right=.92, top=.72, bottom=.16, hspace=.24)
    fig.text(.07, .945, "狮城空气手记  /  DAILY AIR NOTES", color=ink, size=17, weight="normal")
    fig.text(.07, .905, f"{day}  ·  {coverage}  ·  SGT", color="#607575", size=13)
    fig.text(.07, .845, f"{peak:g}", color=ink, size=53, weight="normal")
    fig.text(.30, .848, "μg/m³  /  已获取读数中的最高小时值", color=ink, size=16)
    hour, region = peak_points[0]
    peak_label = f"{REGIONS[region]} {hour:02}:00" + (f" 等 {len(peak_points)} 处并列" if len(peak_points) > 1 else "")
    fig.text(.07, .799, peak_label + f"   ·   有效读数 {count}/120", color=ink, size=14)
    fig.text(.07, .753, "1小时 PM2.5（μg/m³） · 五区共用相同纵轴", color="#607575", size=12)
    for ax, (region, values) in zip(axes, grid.items()):
        ax.set_facecolor("#F6F4EE")
        ax.axhspan(56, min(151, ymax), color="#E8C296", alpha=.22)
        if ymax > 151:
            ax.axhspan(151, min(251, ymax), color="#DF978A", alpha=.18)
        if ymax > 251:
            ax.axhspan(251, ymax, color="#B191B0", alpha=.18)
        for boundary in [56, 151, 251]:
            if boundary < ymax:
                ax.axhline(boundary, color=orange, linestyle=(0, (4, 4)), lw=.7)
        ax.plot(range(24), values, color=teal, lw=2, marker="o", markersize=3)
        ax.text(.01, .78, REGIONS[region], transform=ax.transAxes, color=ink, size=13, weight="normal")
        ax.set_ylim(0, ymax)
        ax.set_xlim(-.3, 23.6)
        ax.set_yticks([0, ymax / 2, ymax])
        ax.grid(axis="y", color="#D7DEDA", lw=.6)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.spines["bottom"].set_color("#D7DEDA")
        ax.tick_params(length=0, labelcolor="#607575")
    axes[-1].set_xticks([0, 6, 12, 18, 23], ["00:00", "06:00", "12:00", "18:00", "23:00"])
    axes[-1].set_xlabel("时间（新加坡 / UTC+8）", labelpad=10, color=ink)
    fig.text(.07, .10, "NEA 1小时分档：0–55 正常 / 56–150 升高 / 151–250 高 / 251及以上 很高", size=11, color=orange)
    fig.text(.07, .073, "来源：NEA / data.gov.sg · 缺测留空，不插值；区域读数不等于个人暴露。", size=10, color="#607575")
    fig.text(.07, .047, "浓度本身不能判定烟霾来源。数据可能经官方后续校正。", size=10, color="#607575")
    output = output or path.parent
    output.mkdir(parents=True, exist_ok=True)
    for extension in ["png", "svg"]:
        target = output / f"pm25-{day}.{extension}"
        fig.savefig(target, dpi=100, facecolor=fig.get_facecolor())
        print(f"数据图已保存：{target}")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    yesterday = datetime.now(SGT).date() - timedelta(days=1)
    for name in ["fetch", "run"]:
        cmd = commands.add_parser(name, help="下载数据" if name == "fetch" else "下载并绘图")
        cmd.add_argument("--date", type=date.fromisoformat, default=yesterday, help="SGT 日期 YYYY-MM-DD，默认昨天")
        cmd.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT)
        if name == "run":
            cmd.add_argument("--font", type=Path)
    cmd = commands.add_parser("plot", help="仅从本地 CSV 绘图，不访问网络")
    cmd.add_argument("--csv", type=Path, required=True)
    cmd.add_argument("--out-dir", type=Path)
    cmd.add_argument("--font", type=Path)
    cmd = commands.add_parser("cards", help="全岛宏观卡 + 带定位地图的五区对比卡")
    cmd.add_argument("--date", type=date.fromisoformat, default=datetime.now(SGT).date())
    cmd.add_argument("--days", type=int, default=7, help="逐日趋势天数（2–31），默认 7")
    cmd.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT)
    cmd.add_argument("--font", type=Path)
    cmd.add_argument("--offline", action="store_true", help="仅用已有 CSV、原始 JSON 和底图缓存重绘")
    args = parser.parse_args()
    try:
        if args.command == "cards":
            from cards import render
            render(args.date, args.days, args.out_dir, args.font, args.offline)
        elif args.command == "plot":
            plot(args.csv, args.out_dir, args.font)
        else:
            path = fetch(args.date, args.out_dir)
            if args.command == "run":
                plot(path, font=args.font)
    except (ValueError, KeyError, OSError, RuntimeError) as exc:
        parser.exit(1, f"错误：{exc}\n")
    except ImportError:
        parser.exit(1, "绘图依赖缺失，请先安装 requirements.txt\n")


if __name__ == "__main__":
    main()
