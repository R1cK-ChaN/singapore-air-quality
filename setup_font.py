#!/usr/bin/env python3
"""Download the pinned KingHwa Old Song font and verify its SHA-256."""
import hashlib
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

FONT = Path(__file__).resolve().parent / "fonts" / "KingHwaOldSong.ttf"
SHA256 = "35d92af5ac4e9485e8e7749098e67211da5885d2697d95aea979fe4acd19ee2a"
URL = ("https://raw.githubusercontent.com/cntrump/imitation_typeface_fonts/"
       "e78093f1b03b8f389815453df4edef809b5d286b/" + quote("京華老宋体v2.002.ttf"))


def main():
    if FONT.is_file() and hashlib.sha256(FONT.read_bytes()).hexdigest() == SHA256:
        print("京华老宋字体已就绪")
        return
    with urlopen(URL, timeout=60) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError("字体校验失败，未安装；请检查下载源")
    FONT.parent.mkdir(parents=True, exist_ok=True)
    temporary = FONT.with_suffix(".tmp")
    temporary.write_bytes(data)
    temporary.replace(FONT)
    print("已安装京华老宋 v2.002（第三方字体，授权见 fonts/README.md）")


if __name__ == "__main__":
    main()
