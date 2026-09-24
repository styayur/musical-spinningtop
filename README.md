# 🎭 Spinning Top · 每日音乐剧

> 打开就转出来一张音乐剧卡片：经典剧照、官方简介、官网与 Fever 演出信息，一天一部。

**Spinning Top** 是一个极轻量的每日音乐剧小应用。运行一个 Python 程序（或打开它托管的网页），
就会以 **3D 卡片** 的形式为你“推送”一部音乐剧：

| 交互 | 效果 |
| --- | --- |
| 🖼️ 卡片正面 | 动态抓取的**经典剧照/海报** |
| 🖱️ 滚轮向下 | 查看 **官方简介**（Wikipedia 实时抓取，经 `deep-translator` **免费**翻译为中文） |
| 👆 左键单击 | 卡片 **3D 翻转**，露出**官网**与 **Fever 演出信息**链接 |

---

## ✨ 特性

- **每日一部**：按日期（一年中的第几天）从片单里轮换，每天打开都是不同剧目；页面上可左右箭头翻看相邻日期、一键“回到今日”。
- **动态抓取**：剧照、海报与简介来自 [Wikipedia API](https://www.mediawiki.org/wiki/API:Main_page)，每次打开都是最新内容。
- **免费翻译**：调用 [`deep-translator`](https://github.com/nidhaloff/deep-translator) 的免费后端
  （Google 翻译 → MyMemory 兜底）把简介翻成中文；翻译结果自动缓存到本地，离线/被限流时回退到内置中文摘要。
- **零密钥**：全程无需任何 API Key，开箱即用。
- **响应式**：手机、平板、桌面均可正常翻转与滚动。

---

## 🚀 快速开始

需要 **Python 3.9+**（已在 3.14 测试）。

### Windows（推荐，双击即可）

双击 `run.bat`。首次运行会自动创建 `.venv` 虚拟环境并安装依赖，然后打开浏览器。

### 通用方式

```bash
# 1) 创建并激活虚拟环境
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

# 2) 安装依赖
pip install -r requirements.txt

# 3) 运行（自动打开浏览器）
python app.py
```

打开 <http://127.0.0.1:5000/> 即可。命令行参数：

```bash
python app.py 8000            # 指定端口
python app.py 8000 --no-browser   # 不自动打开浏览器
```

环境变量：`PORT`（端口）、`NO_BROWSER=1`（不自动打开浏览器）。

---

## 🧠 工作原理

```
python app.py
      │  按“今天”的日序数选一部剧
      ▼
data/musicals.json  ──▶  Wikipedia API（剧照 + 简介 + 图集）
                              │
                              ▼
                    deep-translator 免费翻译（Google → MyMemory）
                              │
                              ▼
               /api/musical  ──▶  浏览器 3D 翻转卡片
```

1. **选片**：`today_musical()` 用 `date.today().toordinal() % len(musicals)` 决定当日剧目，
   因此每天自动轮换，且对所有人一致、可复现。
2. **抓取**：`fetch_wikipedia()` 拉取条目的首段简介（`extracts`）、题图（`pageimages`）与链接；
   `fetch_gallery()` 再取若干张剧照/海报组成图集。
3. **翻译**：`translate_via_deep()` 依次尝试 `GoogleTranslator`、`MyMemoryTranslator`（均为免费、无需密钥）；
   成功结果写入 `data/translations.json` 缓存。若两者都不可用，回退到 `data/summaries_zh.json` 的内置中文摘要。
4. **渲染**：前端单页卡片，滚轮向下看简介，单击翻面看链接。

> 为什么 Fever 链接是 Google 站内搜索？
> Fever（feverup.com）没有稳定的公开搜索 URL，因此链接使用
> `https://www.google.com/search?q=<剧名> site:feverup.com`，能稳定直达该剧在 Fever 上的演出页。

---

## 📁 项目结构

```
musical/_spinningtop
├── app.py                 # Flask 后端：选片、抓取、翻译、接口
├── run.bat                # Windows 一键启动
├── requirements.txt       # 依赖（Flask / requests / deep-translator）
├── data/
│   ├── musicals.json      # 片单（20 部，可自行增删）
│   └── summaries_zh.json  # 内置中文摘要（翻译兜底）
├── templates/
│   └── index.html         # 单页卡片
├── static/
│   ├── style.css          # 剧场风样式 + 3D 翻转
│   └── app.js             # 取数、渲染、翻转、滚动交互
└── LICENSE                # AGPL-3.0
```

## ➕ 添加/修改剧目

编辑 `data/musicals.json`，每部剧一个对象：

```json
{
  "title": "Hamilton",
  "title_zh": "汉密尔顿",
  "wiki": "Hamilton (musical)",
  "year": 2015,
  "composer": "Lin-Manuel Miranda",
  "official_url": "https://hamiltonmusical.com",
  "fever_query": "Hamilton musical"
}
```

- `wiki`：对应英文维基百科的条目名（用于抓取简介与剧照）。
- `fever_query`：用于生成 Fever 演出信息搜索链接。

---

## ⚠️ 说明

- 剧照、海报与简介版权归各自权利人所有，本应用仅通过 Wikipedia API 引用展示，请勿用于商业用途。
- 免费翻译后端（Google / MyMemory）存在速率限制，属正常现象；应用已做缓存与兜底，不影响日常使用。

## 📄 许可证

[AGPL-3.0](./LICENSE) © 2026
