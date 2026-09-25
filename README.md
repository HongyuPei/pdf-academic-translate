# pdf-academic-translate
这是一份基于所提供的技能说明（`SKILL.md`）整理的 **PDF 学术论文翻译与 Markdown 转换工作流 README**。

---

# PDF 论文 → 学术中文 Markdown（含插图与 LaTeX 公式）

## 用途

把一篇 PDF 论文（通常为英文）输出为**可直接阅读、公式可渲染、图表完整**的学术中文 `.md` 交付物，并附带一张置于文首的全文总结性框图。

产出结构：

```text
<workspace>/
├── <论文标题>_中译.md
├── images/Fig00_总结框图.png        # 文首总览框图
├── images/Fig01.png ... FigNN.png   # 原文插图（300 dpi）
└── _build/                          # 中间产物：raw_text.txt、spec json、日志

```

---

## 何时使用

* 用户上传/引用 PDF，要求“翻译成中文”、“写成 `.md`”、“插入图片”、“学术风格”或“公式用 latex”。


* 用户要求“开头生成一个全文总结/逻辑框图”。


* 用户要求“全文翻译”（含附录）或指定只译正文。



---

## 触发前的确认

1. **目标语言**：原文为英文而用户说“翻译成英文”时，往往意指译为中文——先用 `AskUserQuestion` 确认，避免方向做反。


2. **翻译范围**：用户说“全文翻译”时**必须**含致谢、参考文献与全部附录（证明类附录逐节译出，保留原编号如 `(A1)`/`(B9)`）。未说全译时，Methods/Extended Data 可译为“概要”并注明详见原文。


3. **是否要框图**：用户未提则不强加。



---

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

* **注意**：脚本一律用绝对路径调用 `$VENV/Scripts/python.exe`；本机 Git Bash 的 `ls/cat/tail/head/dirname` 不可用，文件操作统一走 Python。



### 1. 抽文本

```bash
"$VENV/Scripts/python.exe" <skill>/scripts/extract_text.py \
    --pdf paper.pdf --out _build/raw_text.txt

```

* 输出按 `===== PAGE n =====` 分段；大文件用 Read 的 `offset`/`limit` 分段读取。


* 加 `--blocks` 可输出带 bbox 的文本块，用于定位图表所在页。



### 2. 抽配图

```bash
"$VENV/Scripts/python.exe" <skill>/scripts/extract_figs.py \
    --pdf paper.pdf --out-dir images --report _build/figs.json

```

* **APS / PRL / 双栏 arXiv 版式（`FIG.` 全大写）**：改用现成脚本 `scripts/extract_figs_aps.py`。


* **Science / Nature 版式**：由于版式特殊（如通栏图、扩展数据图等），需参考 `references/pitfalls.md` 第 2 节进行人工重裁与适配。


* **目视验收**：交付前必须把每张图 Read 一遍做目视验收，确认图例、纵轴标题、刻度、`(a)(b)` 等均在框内。



### 3. 画文首总结框图

先写一份 JSON 规格，再渲染：

```bash
"$VENV/Scripts/python.exe" <skill>/scripts/make_summary_diagram.py \
    --spec _build/summary_spec.json --out images/Fig00_总结框图.png

```

* **推荐 7 层叙事**：研究背景 → 现有方法局限 → 理论核心 → 定理体系 → 方法步骤 → 实验验证 → 结论与意义。


* **注意事项**：字号默认已放大到 1.35（请勿随意更改字号常量）；spec 是纯文本加 `$LaTeX$`，不支持 Markdown；数学片段内不要出现 `%`（防止 mathtext 将其误认为注释符号）。



### 4. 翻译并写 .md

* **公式与参考文献**：动手翻译前先将全部编号公式裁图目视誊录；参考文献单独 dump 成完整文本再誊录，防止长行被截断。


* **结构与排版**：包含头部元信息、翻译说明、总结框图、摘要、各节、结论、致谢/基金、附录与参考文献。行间公式必须写成**三行块形式**（`$$` 独占一行）。



### 5. 交付前自检（必做）

```bash
# (a) 校验公式
NODE_PATH=C:/Users/admin/.workbuddy/binaries/node/workspace/node_modules \
C:/Users/admin/.workbuddy/binaries/node/versions/22.22.2-3/node.exe \
  <skill>/scripts/check_math.js --md paper_zh.md

# (b) 修复数学块
"$VENV/Scripts/python.exe" <skill>/scripts/fix_math_blocks.py --md paper_zh.md

```

* 校验图片引用与文件一一对应、无缺失、无孤立图。整理 `_build/` 目录，保持根目录整洁。



### 6. 收尾

* 在 `images/` 与 `.md` 就位后调用 `present_files` 交付，并在回复中说明全局结论、验证结果及原文笔误/图注问题。
