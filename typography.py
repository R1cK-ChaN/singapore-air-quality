"""Shared typography for every air-quality chart."""
from pathlib import Path


DEFAULT_FONT = Path(__file__).resolve().parent / "fonts" / "KingHwaOldSong.ttf"


def configure_font(font=None, size=12):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import font_manager

    path = Path(font) if font else DEFAULT_FONT
    if not path.is_file():
        raise ValueError("找不到京华老宋字体；请按 fonts/README.md 下载，或用 --font 指定字体文件")
    font_manager.fontManager.addfont(str(path))
    family = font_manager.FontProperties(fname=str(path)).get_name()
    matplotlib.rcParams.update({"font.family": family, "axes.unicode_minus": False,
                               "svg.fonttype": "path", "font.size": size})
