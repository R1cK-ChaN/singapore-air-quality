# 京华老宋

所有空气质量图默认使用特里王制作的京华老宋 v2.002，字体文件放在本目录的 `KingHwaOldSong.ttf`。文件较大，作为本地依赖保存，不提交 Git。

- 字体内部名称：`KingHwa_OldSong`
- [字体文件及附带授权说明的分发仓库](https://github.com/cntrump/imitation_typeface_fonts)
- 固定版本：`e78093f1b03b8f389815453df4edef809b5d286b`
- SHA-256：`35d92af5ac4e9485e8e7749098e67211da5885d2697d95aea979fe4acd19ee2a`
- 授权说明允许免费商用、复制传播和嵌入；字体不是开源软件，不修改或传播修改后的字体文件。

在仓库根目录运行以下命令可下载相同文件：

```bash
python3 - <<'PY'
import hashlib
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

url = 'https://raw.githubusercontent.com/cntrump/imitation_typeface_fonts/e78093f1b03b8f389815453df4edef809b5d286b/' + quote('京華老宋体v2.002.ttf')
with urlopen(url, timeout=60) as response:
    data = response.read()
assert hashlib.sha256(data).hexdigest() == '35d92af5ac4e9485e8e7749098e67211da5885d2697d95aea979fe4acd19ee2a'
Path('fonts/KingHwaOldSong.ttf').write_bytes(data)
PY
```

`typography.py` 统一设置日期、中文标签、数值、坐标轴和脚注字体。SVG 将文字保存为轮廓，便于在没有安装字体的设备上保持一致。OneMap 底图内置文字及原始标志已经栅格化，不属于可替换文本。该字体缺少 ≥ 字符，图例使用“251及以上”表达同一范围。
