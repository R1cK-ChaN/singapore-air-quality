"""Two publication cards from saved NEA observations and a sourced OneMap basemap."""
from __future__ import annotations

import csv
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

from air_quality import REGIONS, SGT, fetch, read_grid
from typography import configure_font

INK, MUTED, PAPER = "#193D3E", "#647779", "#FFFFFF"
TILES = "https://www.onemap.gov.sg/maps/tiles/Grey/{z}/{x}/{y}.png"
LOGO = "https://www.onemap.gov.sg/web-assets/images/logo/om_logo.png"
# Includes the main island, western/southern islands and Pulau Tekong.
BOUNDS = (103.59, 1.16, 104.115, 1.49)
ZOOM = 12


def project(lon, lat, zoom=ZOOM):
    """WGS84 to global XYZ pixel coordinates (Web Mercator, north is up)."""
    size = 256 * 2 ** zoom
    return ((lon + 180) / 360 * size,
            (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * size)


def load_basemap(cache: Path, offline=False):
    from PIL import Image
    cache.mkdir(parents=True, exist_ok=True)
    west, south, east, north = BOUNDS
    left, top = project(west, north)
    right, bottom = project(east, south)
    x0, y0, x1, y1 = [math.floor(v / 256) for v in (left, top, right, bottom)]
    mosaic = Image.new("RGB", ((x1 - x0 + 1) * 256, (y1 - y0 + 1) * 256))
    sources = []
    def asset(url, path):
        if not path.exists():
            if offline:
                raise ValueError(f"离线底图缓存缺失：{path.name}，先执行不带 --offline 的 cards 命令")
            with urlopen(Request(url, headers={"User-Agent": "SG-Air-Notes/1.0"}), timeout=30) as response:
                content = response.read()
            path.write_bytes(content)
        return Image.open(path).copy()
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            url = TILES.format(z=ZOOM, x=x, y=y)
            tile = asset(url, cache / f"grey-{ZOOM}-{x}-{y}.png").convert("RGB")
            if tile.size != (256, 256):
                raise ValueError("OneMap 瓦片尺寸异常")
            mosaic.paste(tile, ((x - x0) * 256, (y - y0) * 256))
            sources.append(url)
    logo = asset(LOGO, cache / "onemap-logo.png")
    manifest = {"tile_urls": sources, "logo_url": LOGO, "bounds_wgs84": BOUNDS,
                "projection": "Web Mercator / XYZ", "attribution": "OneMap © contributors | Singapore Land Authority"}
    (cache / "sources.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return mosaic, (x0 * 256, (x1 + 1) * 256, (y1 + 1) * 256, y0 * 256), logo


def summarize(day, grid):
    hours = [h for h in range(24) if all(math.isfinite(grid[r][h]) for r in REGIONS)]
    latest = max(h for h in range(24) if any(math.isfinite(grid[r][h]) for r in REGIONS))
    # An unequal number of observations must never reweight the regions.
    mean = sum(sum(grid[r][h] for r in REGIONS) / 5 for h in hours) / len(hours) if hours else math.nan
    complete = len(hours) == 24
    through_latest = hours == list(range(latest + 1))
    return {"date": day.isoformat(), "complete_hours": len(hours), "last_hour": latest,
            "daily_mean_ug_m3": mean if complete else math.nan,
            "partial_mean_ug_m3": mean if not complete and through_latest else math.nan}


def limit_grid(grid, cutoff_hour):
    if cutoff_hour is None:
        return grid
    if not 0 <= cutoff_hour <= 23:
        raise ValueError("截止小时必须为 0–23")
    return {region: [value if hour <= cutoff_hour else math.nan
                     for hour, value in enumerate(values)] for region, values in grid.items()}


def prepare(day, days, output, offline, cutoff_hour=None):
    if not 2 <= days <= 31:
        raise ValueError("--days 必须为 2–31")
    today = datetime.now(SGT).date()
    if day > today:
        raise ValueError("不能绘制未来日期")
    summaries = []
    for offset in reversed(range(days)):
        current = day - timedelta(days=offset)
        path = output / current.isoformat() / "pm25.csv"
        fetched = False
        if not offline and (not path.exists() or current == today):
            fetch(current, output)
            fetched = True
        if not path.exists():
            raise ValueError(f"缺少 {current} 的 CSV，请先抓取数据")
        csv_day, grid = read_grid(path)
        # Yesterday's cached daily edition contains only the morning. Complete it
        # before computing full-day means and the next edition's 24-hour window.
        if not offline and not fetched and current < today and any(
                not math.isfinite(v) for values in grid.values() for v in values):
            fetch(current, output)
            csv_day, grid = read_grid(path)
        if csv_day != current:
            raise ValueError(f"{path} 的实际日期与目录不一致")
        if current == day:
            grid = limit_grid(grid, cutoff_hour)
            if not any(math.isfinite(v) for values in grid.values() for v in values):
                raise ValueError("截止时刻之前没有可用数据")
        summaries.append(summarize(current, grid))
    source = json.loads((output / day.isoformat() / "source.json").read_text(encoding="utf-8"))
    metadata = source["pages"][0]["data"]["regionMetadata"]
    locations = {r["name"]: r["labelLocation"] for r in metadata}
    for region in REGIONS:
        point = locations[region]
        if not BOUNDS[0] < point["longitude"] < BOUNDS[2] or not BOUNDS[1] < point["latitude"] < BOUNDS[3]:
            raise ValueError("NEA 区域标注坐标超出地图范围")
    folder = output / day.isoformat() / "cards"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "daily_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=summaries[0])
        writer.writeheader()
        writer.writerows({k: "" if isinstance(v, float) and math.isnan(v) else v for k, v in row.items()} for row in summaries)
    return grid, summaries, locations, folder


def band(value):
    if not math.isfinite(value):
        return "缺测", "#7B8585"
    if value <= 55:
        return "正常", "#25816D"
    if value <= 150:
        return "升高", "#B57A29"
    if value <= 250:
        return "高", "#B54E59"
    return "很高", "#7F527D"


def colored_segments(values):
    """Split plotted connectors at color boundaries, never bridge missing data."""
    segments, colors = [], []
    for x, (start, end) in enumerate(zip(values, values[1:])):
        if not (math.isfinite(start) and math.isfinite(end)):
            continue
        cuts = [0.0, 1.0]
        if start != end:
            cuts += [(boundary - start) / (end - start) for boundary in (55, 150, 250)
                     if min(start, end) < boundary < max(start, end)]
        cuts.sort()
        for left, right in zip(cuts, cuts[1:]):
            y0, y1 = start + left * (end - start), start + right * (end - start)
            segments.append([(x + left, y0), (x + right, y1)])
            colors.append(band((y0 + y1) / 2)[1])
    return segments, colors


def plot_colored_series(ax, values, linewidth, markersize):
    import numpy as np
    from matplotlib.collections import LineCollection
    from matplotlib.colors import to_rgb
    from matplotlib.patches import Polygon
    segments, colors = colored_segments(values)
    # Merge adjacent same-color fills to avoid dark seams at hourly boundaries.
    runs = []
    for (start, end), color in zip(segments, colors):
        if runs and runs[-1][1] == color and runs[-1][0][-1] == start:
            runs[-1][0].append(end)
        else:
            runs.append(([start, end], color))
    for points, color in runs:
        left, right = points[0][0], points[-1][0]
        top = max(y for _, y in points)
        if top <= 0:
            continue
        width = max(32, math.ceil(1200 * (right - left) / max(1, len(values) - 1)))
        xs = np.linspace(left, right, width)
        ys = np.linspace(0, top, 256)[:, None]
        curve = np.interp(xs, [x for x, _ in points], [y for _, y in points])
        height_fraction = np.divide(ys, curve[None, :], out=np.zeros((256, width)),
                                    where=curve[None, :] > 0)
        rgba = np.empty((256, width, 4))
        rgba[:, :, :3] = to_rgb(color)
        rgba[:, :, 3] = .24 * np.clip(height_fraction, 0, 1) ** 1.15
        fill = ax.imshow(rgba, extent=(left, right, 0, top), origin="lower",
                         aspect="auto", interpolation="bilinear", zorder=1)
        outline = [(left, 0), *points, (right, 0)]
        fill.set_clip_path(Polygon(outline, closed=True, transform=ax.transData))
    ax.add_collection(LineCollection(segments, colors=colors, linewidths=linewidth, zorder=3))
    points = [(x, value) for x, value in enumerate(values) if math.isfinite(value)]
    if points:
        ax.scatter([x for x, _ in points], [v for _, v in points], s=markersize ** 2,
                   c=[band(v)[1] for _, v in points], edgecolors="none", zorder=4, clip_on=False)


def rolling_window(day, hour, previous, current):
    """Include both endpoints of the preceding 24 hours: 25 hourly readings."""
    end = datetime.combine(day, datetime.min.time(), tzinfo=SGT).replace(hour=hour)
    times = [end - timedelta(hours=24 - offset) for offset in range(25)]
    series = {region: previous[region][hour:] + current[region][:hour + 1]
              for region in REGIONS}
    return times, series


def render(day: date, days: int, output: Path, font=None, offline=False, cutoff_hour=None):
    grid, summaries, locations, folder = prepare(day, days, output, offline, cutoff_hour)
    basemap, extent, logo = load_basemap(output / "_maps", offline)
    configure_font(font)
    import matplotlib.pyplot as plt
    from matplotlib.offsetbox import OffsetImage, AnnotationBbox

    hour = summaries[-1]["last_hour"]
    snapshot = {r: grid[r][hour] for r in REGIONS}
    current_values = [v for v in snapshot.values() if math.isfinite(v)]
    mean = sum(current_values) / 5 if len(current_values) == 5 else math.nan

    def label(fig, x, y, value, size=14, color=INK, weight="normal", **kwargs):
        return fig.text(x, y, value, fontsize=size, color=color, weight=weight, **kwargs)

    def draw_map(fig, box):
        ax = fig.add_axes(box)
        ax.imshow(basemap, extent=extent, origin="upper", zorder=0)
        left, top = project(BOUNDS[0], BOUNDS[3])
        right, bottom = project(BOUNDS[2], BOUNDS[1])
        ax.set_xlim(left, right)
        ax.set_ylim(bottom, top)
        ax.axis("off")
        for region, point in locations.items():
            if region not in REGIONS:
                continue
            x, y = project(point["longitude"], point["latitude"])
            value = snapshot[region]
            color = band(value)[1]
            text = REGIONS[region] + "\n"
            text += f"{value:g}" if math.isfinite(value) else "缺测"
            ax.scatter(x, y, s=22, facecolor="white", edgecolor=color, lw=1.5, zorder=4)
            ax.annotate(text, (x, y), xytext=(0, 9), textcoords="offset points", ha="center", va="bottom",
                        color="white", fontsize=13, weight="normal", linespacing=1.3,
                        bbox=dict(boxstyle="round,pad=.35,rounding_size=.12", fc=color, ec="white", lw=1.2), zorder=5)
        ax.text(.98, .97, "N ↑", transform=ax.transAxes, ha="right", va="top", color=INK, fontsize=10)
        # Preserve attribution and official logo in each map, including the miniature.
        ax.add_artist(AnnotationBbox(OffsetImage(logo, zoom=18 / logo.height), (.025, .03),
                                    xycoords="axes fraction", frameon=False))
        ax.text(.05, .015, "OneMap © contributors | Singapore Land Authority", transform=ax.transAxes,
                fontsize=7, color=INK, bbox=dict(fc="white", ec="none", alpha=.85, pad=2))
        return ax

    def draw_legend(fig, y):
        for x, value, text in [(.085, 0, "0–55 正常"), (.315, 56, "56–150 升高"), (.555, 151, "151–250 高"), (.785, 251, "251及以上 很高")]:
            label(fig, x, y, "● " + text, 11, band(value)[1])

    def save(fig, name):
        for extension in ["png", "svg"]:
            path = folder / f"{name}.{extension}"
            fig.savefig(path, dpi=100, facecolor=PAPER)
            print(f"数据卡已保存：{path}")
        plt.close(fig)

    # Card 1: a current geographical snapshot plus genuinely daily history.
    fig = plt.figure(figsize=(10.8, 14.4), dpi=100, facecolor=PAPER)
    label(fig, .065, .95, f"{day:%Y.%m.%d}", 16, weight="normal")
    label(fig, .93, .95, "PM2.5", 16, MUTED, ha="right")
    label(fig, .065, .899, f"当前五区均值（截止{hour:02}：00）", 13, MUTED)
    label(fig, .065, .835, f"{mean:.1f}" if math.isfinite(mean) else "—", 47, weight="normal")
    label(fig, .285, .843, "μg/m³", 15, MUTED)
    label(fig, .565, .899, "当前五区范围", 13, MUTED)
    label(fig, .565, .849, f"{min(current_values):g}–{max(current_values):g}", 28, weight="normal")
    draw_map(fig, [.045, .415, .91, .385])
    draw_legend(fig, .39)
    label(fig, .065, .348, f"最近 {days} 天 · 新加坡总体趋势", 17, weight="normal")
    label(fig, .065, .323, "五区日均值的等权平均（μg/m³）", 11, MUTED)
    ax = fig.add_axes([.10, .11, .80, .19], facecolor=PAPER)
    daily = [row["daily_mean_ug_m3"] for row in summaries]
    plot_colored_series(ax, daily, linewidth=2.2, markersize=6)
    for i, value in enumerate(daily):
        if math.isfinite(value):
            ax.annotate(f"{value:.1f}", (i, value), xytext=(0, 9), textcoords="offset points", ha="center", color=band(value)[1], fontsize=11)
    partial = summaries[-1]["partial_mean_ug_m3"]
    if math.isfinite(partial):
        ax.scatter([days - 1], [partial], facecolors=PAPER, edgecolors=band(partial)[1], linewidth=2, s=60, zorder=5)
        ax.annotate(f"{partial:.1f}\n截至{hour:02}时", (days - 1, partial), xytext=(0, 10), textcoords="offset points",
                    ha="center", fontsize=10, color=band(partial)[1])
    finite = [v for v in daily + [partial] if math.isfinite(v)]
    ymax = max(50, math.ceil(max(finite, default=0) * 1.4 / 25) * 25)
    ax.set_ylim(0, ymax)
    ax.set_xlim(-.4, days - .25)
    tick_step = max(1, math.ceil(days / 8))
    ticks = sorted(set(list(range(0, days, tick_step)) + [days - 1]))
    ax.set_xticks(ticks, [summaries[i]["date"][5:].replace("-", "/") for i in ticks])
    ax.set_yticks([0, ymax / 2, ymax])
    ax.grid(axis="y", color="#DCE1DD", lw=.7)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color("#DCE1DD")
    ax.tick_params(length=0, labelsize=10, colors=MUTED)
    label(fig, .065, .04, "来源：NEA / data.gov.sg", 10, MUTED)
    save(fig, "01-island-overview")

    # Card 2: positional orientation, matched colors, and comparable hourly scales.
    fig = plt.figure(figsize=(10.8, 14.4), dpi=100, facecolor=PAPER)
    label(fig, .065, .95, f"{day:%Y.%m.%d}（截止{hour:02}：00）", 16, weight="normal")
    label(fig, .93, .95, "1小时 PM2.5（μg/m³）", 13, MUTED, ha="right")
    draw_map(fig, [.065, .505, .87, .41])
    draw_legend(fig, .482)
    previous_day = day - timedelta(days=1)
    _, previous_grid = read_grid(output / previous_day.isoformat() / "pm25.csv")
    times, window = rolling_window(day, hour, previous_grid, grid)
    values = [v for items in window.values() for v in items if math.isfinite(v)]
    ymax = max(160, math.ceil(max(values) / 50) * 50)
    ticks = [0, 6, 12, 18, 24]
    tick_labels = [times[t].strftime("%m/%d\n%H:%M" if t in (0, 24) else "%H:%M") for t in ticks]
    for i, (region, items) in enumerate(window.items()):
        y = .405 - i * .075
        value = snapshot[region]
        color = band(value)[1]
        ax = fig.add_axes([.18, y, .64, .058], facecolor=PAPER)
        plot_colored_series(ax, items, linewidth=2.1, markersize=2.5)
        ax.set_ylim(0, ymax)
        ax.set_xlim(0, 24)
        ax.set_yticks([0, ymax])
        ax.tick_params(length=0, colors=MUTED, labelsize=9)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.spines["bottom"].set_color("#DCE1DD")
        ax.set_xticks(ticks, tick_labels if i == 4 else [""] * 5)
        label(fig, .065, y + .023, REGIONS[region], 15, color, weight="normal")
        label(fig, .865, y + .023, f"{value:g}" if math.isfinite(value) else "—", 23, color, weight="normal")
    label(fig, .51, .067, "时间（新加坡）", 10, MUTED, ha="center")
    label(fig, .065, .027, "来源：NEA / data.gov.sg", 10, MUTED)
    save(fig, "02-regional-comparison")
    return folder
