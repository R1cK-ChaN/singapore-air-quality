# 新加坡空气质量，每天两张图

用 Agent 把工具搭好，让代码每天取数、计算、出图。

[English](README.en.md) · [快速开始](#快速开始) · [怎么和-agent-一起做的](docs/build-with-agent.md) · [完整使用说明](docs/usage.md)

最近新加坡有雾霾，我想看清五个区域的 PM2.5，以及和昨天相比有什么变化。于是和 Agent 一起做了这个小工具，也把代码放在这里，方便大家自己运行或修改。

数据来自 **NEA / data.gov.sg**，地图来自 **SLA OneMap**。每天等五区 **11:00（新加坡时间）** 的读数齐全，再生成两张图片。取数、计算和绘图使用 Python 脚本，运行脚本无需调用语言模型。

## 生成的图片

下面是 **2026-09-30 截至11:00的历史示例**，用于展示版式，不是实时读数。点击可查看原图。

| 全岛空气卡 | 五区24小时对比 |
| :---: | :---: |
| [![全岛空气卡：区域读数与最近七天趋势](assets/2026-09-30-overview.png)](assets/2026-09-30-overview.png) | [![区域对比：昨日11点至今日11点的五区曲线](assets/2026-09-30-regions.png)](assets/2026-09-30-regions.png) |
| 地图、当前五区均值、最近七天趋势 | 区域位置、当前读数、过去24小时变化 |

PNG 为 **1080 × 1440**，同时输出 SVG。曲线按每个点的浓度换色，缺测处留空；京华老宋字体、纯白背景和渐变填色都由代码统一设置。

## 快速开始

需要 Python 3.10+ 和网络。以下命令适用于 macOS / Linux。

```bash
git clone https://github.com/R1cK-ChaN/singapore-air-quality.git
cd singapore-air-quality
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python setup_font.py
.venv/bin/python daily.py
```

请在新加坡时间11:00之后运行每日版。它会检查五区11:00数据，每60秒重试，最多等待60分钟；超时或取数失败会报告错误。

Windows PowerShell 用户可用 `py -3 -m venv .venv` 创建环境，并将命令中的 `.venv/bin/python` 换成 `.venv\Scripts\python.exe`。

想随时试跑，可以指定历史日期：

```bash
.venv/bin/python daily.py --date 2026-09-30
```

产物保存在 `output/YYYY-MM-DD/cards/`：

- `01-island-overview.png` / `.svg`：全岛空气卡。
- `02-regional-comparison.png` / `.svg`：五区对比卡。
- `daily_summary.csv`：多日统计。
- `daily_run.json`：运行状态；`status=complete` 表示本次生成完成。

原始响应和逐小时 CSV 也会按日期保存。首次运行需要下载七天数据与地图瓦片；之后可复用缓存。[更多命令与离线重绘](docs/usage.md)

首次下载若遇到 `HTTP 429`，表示官方接口限流。稍等一两分钟后重跑同一条命令，已下载的历史文件会被复用。

## Agent 做什么，代码做什么

这个项目是边看结果边改出来的：地图放大、字体更换、折线时间窗口调整，以及超过55以后及时换色，都是实际使用时提的修改。

| 工作 | 怎么完成 |
| --- | --- |
| 找数据源、写程序、修改样式、排查问题 | 开发时由人与 Agent 一起完成 |
| 下载数据、检查时点、计算均值、生成图片 | 每次运行同一套 Python 脚本 |
| 定时启动、检查进程、发送通知 | 根据运行环境单独配置 |

固定规则写进代码以后，每天不必让模型重新查数和组织图表，可以减少模型调用，也减少数字在生成过程中被误写的机会。程序仍然需要检查，我们保留原始数据并测试日期、缺失值和分档边界。

**[阅读这个项目的制作过程 →](docs/build-with-agent.md)**

## 每天怎么跑

建议把 `daily.py` 安排在新加坡时间 **11:05** 启动。先等当天11:00数据齐全，再刷新不完整的历史缓存、生成图片并记录结果。

仓库不附带已启用的定时任务，也不调用 LLM API。可以用系统定时器执行同一个命令。作者目前使用本地 Codex 定时任务启动与通知，这部分仍有模型调用，需要电脑和应用保持运行；克隆仓库不会复制这项个人配置。

## 数据怎么算

- 展示 **1小时 PM2.5 浓度（μg/m³）**。PSI、AQI 是不同指标。
- 当前五区均值为五个区域等权平均；历史日均先求各小时五区均值，再平均一天24小时，属于自算统计。
- 当天截至11点的均值用空心点表示，与完整日均分开。历史数据缺少任一区任一小时，不画成完整日均值。
- 曲线以 **55、150、250** 为换色边界。分档颜色用来表达浓度；日均曲线颜色不等于官方健康等级。
- 地图位置来自官方区域参考坐标，不能代表精确监测站或行政区边界。观测数据本身不能证明污染来自哪里。

[完整统计口径与缓存规则](docs/usage.md#两张卡的统计和地图口径)

## 修改与反馈

想改配色、地图和排版，从 [`cards.py`](cards.py) 开始；每日流程在 [`daily.py`](daily.py)。取数与CSV处理在 [`air_quality.py`](air_quality.py)，字体设置在 [`typography.py`](typography.py)。

```bash
python3 -m unittest discover -s . -p 'test_*.py' -v
```

遇到问题，欢迎[提 Issue](https://github.com/R1cK-ChaN/singapore-air-quality/issues)，附上运行命令、出图日期和错误信息。请去掉 API key 等个人信息。也欢迎提交改进版式或修复问题的 PR。

## 来源与许可

- 数据：[NEA / data.gov.sg](https://data.gov.sg/datasets/d_e1058d6974c877257e32048ab128ad83/view)
- 底图：[SLA OneMap](https://www.onemap.gov.sg/)，图片保留原有署名。
- 字体：[京华老宋 v2.002](fonts/README.md)，单独下载并校验，字体文件不随仓库分发。

代码和原创文档采用 [MIT License](LICENSE)。第三方数据、地图、字体及其在示例图中的内容仍适用各自条款，详见 [来源说明](THIRD_PARTY_NOTICES.md)。
