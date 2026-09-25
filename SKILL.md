---
name: pdf-academic-translate
description: 把 PDF 学术论文译为专业学术中文 Markdown（.md）并插入原文插图、公式用 LaTeX。当用户上传 PDF/文献并要求“翻译成中文 / 写成 .md / 插入图片 / 学术写作风格 / 公式用 latex / 开头加总结框图”时使用。
agent_created: true
---

# PDF 论文 → 学术中文 Markdown（含插图与 LaTeX 公式）

## 用途
把一篇 PDF 论文（通常为英文）输出为**可直接阅读、公式可渲染、图表完整**的学术中文 `.md` 交付物，并附带一张置于文首的全文总结性框图。

产出结构：
```
<workspace>/
├── <论文标题>_中译.md
├── images/Fig00_总结框图.png        # 文首总览框图
├── images/Fig01.png ... FigNN.png   # 原文插图（300 dpi）
└── _build/                          # 中间产物：raw_text.txt、spec json、日志
```

## 何时使用
- 用户上传/引用 PDF，要求"翻译成中文""写成 .md""插入图片""学术风格""公式用 latex"。
- 用户要求"开头生成一个全文总结/逻辑框图"。
- 用户要求"全文翻译"（含附录）或指定只译正文。

## 触发前的确认
1. **目标语言**：原文为英文而用户说"翻译成英文"时，往往意指译为中文——先用 AskUserQuestion 确认，避免方向做反。
2. **翻译范围**：用户说"全文翻译"时**必须**含致谢、参考文献与全部附录（证明类附录逐节译出，保留原编号如 `(A1)`/`(B9)`）。
   未说全译时，Methods/Extended Data 可译为"概要"并注明详见原文。
3. **是否要框图**：用户未提则不强加。

## 执行流程

### 0. 准备环境（一次性）
```bash
PY=C:/Users/admin/.workbuddy/binaries/python/versions/3.13.12/python.exe
VENV=C:/Users/admin/.workbuddy/binaries/python/envs/default
"$PY" -m venv "$VENV"
"$VENV/Scripts/python.exe" -m pip install pymupdf matplotlib

mkdir -p C:/Users/admin/.workbuddy/binaries/node/workspace
cd C:/Users/admin/.workbuddy/binaries/node/workspace && \
  C:/Users/admin/.workbuddy/binaries/node/versions/22.22.2-3/npm.cmd install katex
```
脚本一律用绝对路径调用 `$VENV/Scripts/python.exe`；本机 Git Bash 的 `ls/cat/tail/head/dirname` 不可用，文件操作走 Python。

### 1. 抽文本
```bash
"$VENV/Scripts/python.exe" <skill>/scripts/extract_text.py \
    --pdf paper.pdf --out _build/raw_text.txt
```
- 输出按 `===== PAGE n =====` 分段；大文件用 Read 的 `offset`/`limit` 分段读取。
- 加 `--blocks` 可输出带 bbox 的文本块，用于定位图表所在页。
- 脚本会报告内嵌位图数量：为 0 说明插图全是矢量，配图只能走区域渲染。

### 2. 抽配图
```bash
"$VENV/Scripts/python.exe" <skill>/scripts/extract_figs.py \
    --pdf paper.pdf --out-dir images --report _build/figs.json
```
- 默认自动扫描全部含图注（`Fig.` / `Figure`）的页；也可用 `--pages 11,12,14` 指定。
- 算法要点：版带定位 + 并排版式判定 + 页眉钳制 + 邻近标签吸收。
- **APS / PRL / 双栏 arXiv 版式（`FIG.` 全大写）改用现成脚本 `scripts/extract_figs_aps.py`**，
  它已内置大写图注正则 + 按栏切分 + 整栏取宽，直接调用即可：
  ```bash
  "$VENV/Scripts/python.exe" <skill>/scripts/extract_figs_aps.py \
      --pdf paper.pdf --out-dir images --report _build/figs.json
  ```
  （`extract_figs.py` 的 `^(Fig\.|Figure)` 匹配不到 `FIG. 1.`，会报 "figures written: 0"。）
- **Science / AAAS 版式（图注 `Fig. 1.`）会漏裁且首图必被截断，需手工定 clip**：
  Science 首图常是**五联通栏图**（横跨整页宽），而 Fig. 2/3 在左栏、Fig. 4 在右栏，且**图注多在图下方**。
  此时 clip 下界要取 `图注.y1 + 2`（把图注一并裁进来），左右边界按**图形并集**而非整栏。
  实测参数与逐图对照表见 `references/pitfalls.md` 第 2 节"Science / AAAS 版式"。
- **Nature / Springer 双栏版式（图注 `Fig. 1 |`、扩展数据图 `Extended Data Fig. 1 |`）要人工重裁**：
  图注常只占左栏而图形是**四联通栏**，脚本会切掉右半幅；左边界若用 `x0=52` 还会切掉面板字母 `a`
  （应在 40）。**扩展数据图 APS 脚本完全匹配不到，须自写脚本按"图形并集 + 上下判据 + 页眉钳制 44"处理。**
  做法与实测参数见 `references/pitfalls.md` 第 2 节"Springer / Nature 双栏版式"。
- **实现细节与必须避开的坑见 `references/pitfalls.md` 第 2 节**（尤其 `get_text("blocks")` 的元组顺序）。
- **交付前必须把每张图 Read 一遍做目视验收**，确认图例、纵轴标题、刻度、`(a)(b)`、colorbar、图内器件名、四条边线都在框内。

### 3. 画文首总结框图
先写一份 JSON 规格（结构可照抄本次交付的 `_build/summary_spec.json`），再渲染：
```bash
"$VENV/Scripts/python.exe" <skill>/scripts/make_summary_diagram.py \
    --spec _build/summary_spec.json --out images/Fig00_总结框图.png
```
规格约定：`blocks` 自上而下排布，每块 `kind` 取 `text` / `formula` / `steps` / `grid`，
`color` 取 `ctx`/`prob`/`core`/`thm`/`method`/`exp`/`res`。
推荐 7 层叙事：**研究背景 → 现有方法局限 → 理论核心 → 定理体系 → 方法步骤 → 实验验证 → 结论与意义**。

脚本能力与使用要点：
- **文本自动折行**：按画布实际宽度测量（中英混排 + 行内 `$LaTeX$` 片段），含中文避头尾，不会溢出边框；
  spec 里的 `lines` / `body` 无需手工折行，`\n` 仅作强制换行。
- **字号默认已放大到 1.35**（正文 11.4pt→15.4pt、标签 13.5→18.2pt、标题 18.5→25.0pt）：
  这是本用户的既定偏好，**不要传 `--font-scale`、也不要改脚本里的字号常量**，直接默认出图即可。
  需要更紧凑时再显式给 `--font-scale 1.0–1.2`；块高会按字号自动重算，不会溢出。
- 放大字号的原理是"字号增大而画布宽度不变 → 每行字数减少 → 文字占画布比例变大"；
  只调 `--width` 不同步调字号等于没变（显示时会被缩放回去）。
- **spec 是纯文本 + `$LaTeX$`，不支持 Markdown**：写 `**粗体**` 会原样显示星号；
  Unicode 上下标 `³P₀`/`¹⁷¹Yb`/`T₂`/`|0⟩` 在 msyh 下**缺字形渲染成方框**，
  必须改写成 `$^{3}P_{0}$`/`$^{171}$Yb`/`$T_{2}$`/`$|0\rangle$`。
  改 spec 一律 `json.load` → 改字符串值 → `json.dumps`，**不要对 JSON 文本做替换**（`\times` 会被写成 TAB 字符）。
  详见 `references/pitfalls.md` §3.0.2 与 §3.0.3。
- **spec 里数学片段内不要出现 `%`**：mathtext 把 `%` 当注释符，会让结尾的 `$` 变成多余字符并报
  `ParseException: Expected end of text`（报错位置指向行首，极具误导性）。
  写成 `$F\geq95.0(2)$%`，把百分号放在数学片段之外。详见 `references/pitfalls.md` §3.0.1。
- 渲染后**必须目视检查一遍**：重点看每块末行是否在框内、有无单字孤行、公式是否溢出。
  框图通常很高（2340 × 3729 px），整张看会糊 —— 用 PIL 纵向切成 3 段再逐段 Read。
  实现细节与三个致命坑（坐标轴留白、px/pt 单位、行高倍率）见 `references/pitfalls.md` 第 3 节。

### 4. 翻译并写 .md
- **动手翻译前先把全部编号公式裁图目视誊录**：`get_text("blocks")` 会把带上下标的公式打散成十几个碎片、
  顺序不可靠，凭碎片拼公式极易写错正负号与上下标。把每个公式区域按 420 dpi 单独渲染再 Read 誊录，
  一次可定案（做法见 `references/pitfalls.md` 第 2 节末）。
- 参考文献同样要**先单独 dump 成完整文本**再誊录：raw_text 把块内换行压成空格，长行会被 Read 截断。
- 结构：头部元信息（标题/作者/机构/期刊/DOI/收稿日期）→ 版权与翻译说明 → **总结框图** → 摘要 → 关键词 → 各节 → 结论 → 致谢/贡献/基金/数据可用性/利益冲突 → 附录 → 参考文献。
  头部/机构行建议各写成 `- ` 列表项，否则 Markdown 会把多行并成一段。
- 公式：行内 `$...$`；行间必须写成**三行块形式**（`$$` 独占一行）。**这是硬性要求**，理由见 `references/pitfalls.md` 第 1 节。
- 图表就近插入，用相对路径 `images/FigNN.png`，配中文图注（`*图 N　...*`）。
- 术语全篇统一；数字与单位严格照抄（如 `2.14(13)×`、`0.62(3)%`）。
- 参考文献保留原文著录格式不翻译。
- 原文明显笔误以「**译注**」标出，不改动推理链条。

### 5. 交付前自检（必做，缺一不可）
```bash
# (a) 公式：全部通过，并确认无"单行 $$"残留
NODE_PATH=C:/Users/admin/.workbuddy/binaries/node/workspace/node_modules \
C:/Users/admin/.workbuddy/binaries/node/versions/22.22.2-3/node.exe \
  <skill>/scripts/check_math.js --md paper_zh.md
# 期望输出最后一行 ALL CHECKS PASSED

# (b) 若 .md 是分段写入的（如 p1/p2/p3.md 再由脚本拼接），先跑一次靠写转换
"$VENV/Scripts/python.exe" <skill>/scripts/fix_math_blocks.py --md paper_zh.md

# (c) 校验图片引用与文件一一对应、无缺失、无孤立图
```
```python
# (c) 的具体做法
import io, os, re
s = io.open(md, encoding="utf-8").read()
refs = re.findall(r'!\[[^\]]*\]\(([^)]+)\)', s)
assert not [p for p in refs if not os.path.exists(p)], "有图片路径失效"
assert set(os.listdir("images")) == {os.path.basename(p) for p in refs}, "存在孤立图片或有图未引用"
```
- 整理 `_build/`：把脚本、原始文本、日志、`.bak` 全部移入，保持根目录只有 `.md` + `images/` + `_build/`。
- **不要生成 HTML 预览**（用户明确不需要）；除非用户主动要求。

### 6. 收尾
- 在 `images/` 与 `.md` 中就位后调用 present_files 交付：优先放 `.md`，其次放关键图。
- 在回复中说明：全局结论、公式与图片的验证结果、以及发现的原文笔误/图注问题。

## 参考
- `references/pitfalls.md` —— 公式渲染陷阱（单行 `$$` + `\tag`）、KaTeX 常见语法错、
  配图裁切的四个坑（元组顺序 / 并排版式 / 页眉钳制 / 目视验收）、matplotlib mathtext 限制、本机环境与交付约定。
  **执行第 2、3、4 步前先读一遍。**
