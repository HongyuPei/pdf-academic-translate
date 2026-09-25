# 踩坑与自检清单

本文件记录实际交付中踩过的坑与验证手段。SKILL.md 只保留流程，细节在此查阅。

---

## 1. 公式：LaTeX 写对了也可能"渲染不出来"

### 症状
用户反馈"这些行间公式没有用 latex 么？"——源文件里明明是 `$$...$$`，`$` 也成对，但在编辑器/预览里显示为 LaTeX 源码。

### 根因
```
$$ \varepsilon_t(\rho)=p_t\rho+z_t, \tag{18}$$      ← 错误：单行
```
- 多数 Markdown 渲染器（VS Code 内置预览、markdown-it-katex 系）**只把独占一行的 `$$` 识别为 display 公式**；
  写在一行的 `$$...$$` 会被判为**行内**公式。
- KaTeX 的 `\tag{}` **只允许在 display 模式下使用**，行内模式直接抛错；
- 渲染器遇到公式编译失败 → **回退成显示 LaTeX 源码**，看起来就像"完全没用 LaTeX"。

实测数据：某次交付 110 条行间公式中 102 条带 `\tag`，单行写法下行内模式 **102/102 全部失败**。

### 正确写法
```
$$
\varepsilon_t(\rho)=p_t\rho+z_t,\qquad z_t\in\mathbb{Z}^{N}, \tag{18}
$$
```
前后各留一个空行。改写用 `scripts/fix_math_blocks.py`。

### 验证
```bash
NODE_PATH=C:/Users/admin/.workbuddy/binaries/node/workspace/node_modules \
C:/Users/admin/.workbuddy/binaries/node/versions/22.22.2-3/node.exe \
  scripts/check_math.js --md paper_zh.md
```
脚本会分别以 `displayMode=true/false` 编译全部公式，并做一次"行间公式按 inline 渲染"的对照实验。
**必须看到 `ALL CHECKS PASSED`**。

### KaTeX 常见语法错
| 错误 | 原因 | 改法 |
|---|---|---|
| `Double subscript` | `\sigma_j^{\otimes N}_{j=1}` 同一基底出现两个 `_` | `\bigotimes_{j=1}^{N}\sigma_j` |
| `\tag works only in display equations` | 见上 | 改成独立行块 |
| 整段异常 | 某行 `$` 个数为奇数，定界符未闭合 | 逐行统计 `$` 奇偶 |

注意：`Z^{\otimes N}_{j=1}`（先上标后下标）是**合法**的，只有"两个下标"才报错。

---

## 2. 配图：大多是矢量，只能"区域渲染"

### 先判断有没有位图可提
```python
n = sum(len(doc[i].get_images(full=True)) for i in range(doc.page_count))
```
- Springer / Elsevier 等排版的论文，插图**几乎全是纯矢量绘制**。
  实例：38 页论文内嵌位图 **0 个**——不存在"直接提图"的选项。
- 此时"裁切"实质是**把矢量区域按 300 dpi 渲染成栅格**，属矢量→栅格的无损路径，
  质量优于任何位图截图。**应主动向用户说明这一点**，避免被理解为"低质量截图"。

### 致命陷阱：`get_text("blocks")` 的元组顺序
返回 **`(x0, y0, x1, y1, text, block_no, block_type)`**。
```python
for cy0, cy1, cx0, cx1, t in caps:      # ✗ cy0 实际拿到 x0≈51（左边距）
for cx0, cy0, cx1, cy1, t in caps:      # ✓
```
写错时**不会报错**，只会让候选筛选静默全部落空、裁切位置整体失准（表现为"所有图都走了兜底分支"）。

### 版带（band）法
对页面上第 k 个图注：
- `band_top` = 上一条图注的 `y1`（首条用页眉下沿 ≈ 52）
- `band_bottom` = 下一条图注的 `y0`（末条用 `H - 40`）
- 只取落在版带内的 `get_drawings().rect` 与 `get_image_info().bbox` → 避免跨图串味

### 判定"图注与插图并排"
图注在左列、插图在右列是常见版式。判据：
并集 **起始于图注顶附近**（`U.y0 >= cy0 - 8`）且 **纵向远超图注底**（`U.y1 > cy1 + 10`）。
此时改用**整个版带**的图形并集，`clip.y1 = U.y1 + 14`。

**反例（曾犯）**：用 `cy0-40 < y0 < cy1+40` 按图注高度限定筛选——
会把下半幅图（如图中下半圈量子比特与器件名）**直接切掉**。

### 边界与内边距
```python
top    = max(U.y0 - 26, band_top + 3)     # 必须用 band_top 钳制！
bottom = cy0 - 2                          # 固定到图注顶
clip   = pymupdf.Rect(U.x0 - 14, top, U.x1 + 14, bottom) & page_safe_area
```
- 上边距 26 用于吸收子图标题 / `(a)(b)` / 坐标轴标题；
- **必须钳制到 `band_top + 3`**，否则会把页眉 `Journal name... Page 11 of 38 213`（y ≈ 33–41）裁进图里；
- 下边界固定为图注顶，既保证 x 轴标题、`Cases/Method`、`(a)(b)` 在内，又天然不会吃到图注文字。

### 必须逐张目视验收
几何启发式无法保证完备。交付前把全部图 `Read` 一遍，逐一确认：
**图例 / 纵轴标题 / 刻度 / `(a)(b)` / 色标 colorbar / 图内器件名 / 四条边线**是否都在框内。
实例：仅靠公式化 padding 无法发现 Fig.15 被切掉下半圈、Fig.10 被切掉 colorbar。

### 图注也要核对
裁切后看图会发现原文图注与自己的中文图注不一致。实例：
某论文 Fig.14 实含 ibm_lagos + ibm_perth **两幅子图**（原写只标了前者）；
Fig.15 图内印着 `ibm_osaka`，而中文图注误标为 `ibm_perth`。**以图面内容为准修正。**

### 双栏 arXiv/APS 排版的额外问题（`FIG.` 全大写 + 分栏）
**已内置现成脚本：`scripts/extract_figs_aps.py`（实测可用，直接调用，不必再改写）。**
```bash
"$VENV/Scripts/python.exe" <skill>/scripts/extract_figs_aps.py \
    --pdf paper.pdf --out-dir images --report _build/figs.json
```
已参数化：`--header-bottom`（页眉下沿，PRL 为 40）、`--col-split`（默认 306）、
`--full-width`（图注宽 > 此值判通栏）、`--column x0,x1`（可重复，手动指定栏目）。
实测：PRL 6 页 / 4 图（Fig.1 左栏、Fig.2 左栏、Fig.3 右栏、Fig.4 右栏）一次全部裁对，
与手工改写版结果一致（仅差 0.1pt 边界）。

原 `extract_figs.py` 的 `CAP_RE = ^(Fig\.|Figure)` **匹配不到 `FIG. 1.`**，
直接跑会报 "figures written: 0"。若需自行改写，按下面三点：

1. 图注正则改 `re.compile(r'^FIG\.\s*(S?)(\d+)\b', re.I)`；
2. **按栏切分**：图注宽度 > 400pt ⇒ 通栏图（x 取整页版心），否则按 x0 < 306 判左/右栏，
   band 只在同栏内推进（否则左栏图注会截断右栏图的 band）；
3. 横向一律取**整栏宽度**而不是图形并集 —— 轴标题、刻度、(a)(b) 都是文字块、
   不在 `get_drawings()` 里，用并集会把 `Ω/2π (MHz)` 这类旋转轴标题切掉。

实例：15 页 arXiv 论文（4 主图 + 9 附录图，其中 2 页各含两幅图）一次全部裁对。

### Springer / Nature 双栏版式（图注占单栏、图形却可能通栏）
**`extract_figs_aps.py` 对 Nature 文章只能算"半可用"，必须人工复核并按需重裁。**
Nature Article 的版心是两栏（左 40–296、右 306–563），但：
- 图注可能**只印在左栏**，而图形是**四联通栏**（实例：Nature 621, 728 的 Fig. 2 = a|c 左 + b|d 右，Fig. 3 = a b c d 一排通栏）。
  脚本按"图注所在栏"取宽 → 右半幅被整块切掉，且左边缘 `x0=52` 会**切掉面板字母 `a`**（字母在 x≈45）。
- 一页内可能有**两个图**（上为通栏 Fig.3、下为右栏 Fig.4），band 逻辑会把上图的图注文字一路吃进下图的 clip
  （实测 Fig.4 得到 clip y 42–684.7，裁进半页正文与图注）。

**判定与处置（实测一次全部裁对）**：
1. `x0` 左边界统一取 **40.0**（不是 52）；右边界单栏取 302–304、通栏取 566。
2. 先算该图 "图形/位图并集" 宽度：`> 380pt ⇒ 通栏`（x 取 38–566），否则取图形并集外扩 22pt。
3. 通栏四联图的图注是**通栏两栏并排**的（左栏 + 右栏各有文本块），可用"图注块 x 跨度 > 400pt"识别。
4. 收尾一律**逐张 Read 目视验收**：重点看右边缘是否被切（纵轴标题 `2|⟨Jy⟩|/N` 是否只剩一半）、面板字母 a/b/c/d 是否齐全。
5. 图注格式：Nature 用 `Fig. 1 |`、扩展数据图用 `Extended Data Fig. 1 |`（**两者 APS 脚本的正则都匹配不到**，扩展数据图需自写）。

### 扩展数据图（Extended Data）单独处理
Nature 的扩展数据图**每页恰好一图一注**，最稳的做法是"整页图形并集 + 上下判据"：
```python
CAP_RE = re.compile(r'^Extended Data Fig\.\s*(\d+)\s*\|', re.I)
# 图形并集 = get_drawings().rect + get_image_info().bbox，剔除落在图注框内的
# 分别算"注以上/注以下"的图形总面积，取面积大的一侧为图形所在侧
top = max(U.y0 - 18, 44.0)        # 44.0 是页眉 "Article"(y 24.8–42.5) 的下沿，必须钳制
bottom = min(U.y1 + 10, cap.y0 - 2)
```
- **页眉钳制取 44 而不是 40**：取 40 会把页眉文字下沿的残影裁成图片顶部的一条横线。
- 统计"图形面积"时要把**图注自身的矩形排除**，否则图注所在侧总面积虚高、判据翻车。

### Science / AAAS 版式（图注 `Fig. 1.`，通栏大字标题 + 双栏正文）
**`extract_figs.py` 对 Science 文章只能裁出约 3/4 的图，且首图必被截断，需按下列规则手工定 clip。**
实测参数（Science 单页宽 **594 pt**，页眉 y≈33–42，故钳制下沿取 **46**；左栏 x 30–300、右栏 x 302–570）：

| 图 | 版面 | clip |
|---|---|---|
| Fig. 1 | **五联通栏**（横跨全页宽，A–C 三面板 + 右侧 Loading 区） | `(40, 46, 572, 图注.y0-4)` |
| Fig. 2 | 左栏，8 面板 A–H，图注**位于图下方** | `(34, 图形.y0-14, 296, 图注.y1+2)` |
| Fig. 3 | 左栏，A–E，图注在图下方 | `(50, 图形.y0-6, 280, 图注.y1+2)` |
| Fig. 4 | 右栏，A–E，图注在图下方 | `(306, 图形.y0-6, 563, 图注.y1+2)` |

要点：
1. **图注在图下方时，clip 必须包含图注**（下界取 `图注.y1 + 2`），否则中文图注与图面对不上；
   但**左/右边界要按图形并集外扩、而不是整栏**——Fig. 3 图形并集 x 为 57–273，用整栏 x 会在左侧带进正文空列。
2. **通栏图的右边界不要取满 570**：Fig. 1 图形并集右缘 468，但右侧还有「Loading」区域与斜穿整页的 dipole trap 虚线，
   取到 572 才能保证该区域不被切掉。
3. 图形并集**先按"图注所在栏"筛 y 带**再取并集，否则会串入相邻图。
4. 交付前**逐张 Read**：本版式最容易漏的是最右侧面板与最下方子图标题。

### 长文本块与参考文献的完整获取
- `raw_text.txt` 把 PDF 文本块的**内部换行压成了空格**，于是一整页参考文献变成一行；
  而 Read 会**截断超过 2000 字符的行**，表现为结尾出现 `... [truncated]`，参考文献会丢失一部分。
- 需要完整誊录参考文献时，单独写脚本把块按原样 dump（保留内部 `\n`），再 Read：
  ```python
  for b in page.get_text("blocks"):
      t = b[4]
      if "doi" in t or "Preprint" in t or "Phys." in t:   # 参考文献块特征
          buf += [t.strip(), ""]
  ```
- 实例：Nature 论文 53 条参考文献分布在 p5 右栏、p6 左右栏、p9 右栏共 5 个块里，直接读 raw_text 会丢 ~30 条。

### 编号公式：不要从 block 碎片拼，直接裁图目视誊录
带上下标、分式、括号的编号公式在 `get_text("blocks")` 里会被打散成十几个碎片
（`[x 171-173 y 464.1-471.2] i` 之类），顺序不可靠，靠碎片拼公式**极易出错**。
正确做法：把公式所在区域按 **420 dpi** 单独渲染成小图，再 Read 目视誊录：
```python
doc[page_index].get_pixmap(clip=pymupdf.Rect(x0, y0, x1, y1), dpi=420).save("eq/eq1.png")
```
实测收益：一次交付中 4 条编号公式全部靠此法定稿；同时顺带发现了
"Measured = (N/2)(ε↓−ε↑) + (1−ε↓−ε↑)⟨J̃⟩" 这类**符号易错项**（凭碎片重建几乎必然写错正负号）。

---

## 3. matplotlib 画总结框图的坑

### 3.0.1 `%` 在 mathtext 里是**注释符**（最易漏，且报错信息很有误导性）
spec 里写 `"$F\\geq95.0(2)%$"` 会抛：
```
ParseException: Expected end of text, found '$'  (at char 5)
```
报错位置指向**行首**、且提示 "Expected end of text"，看起来像 delimiters 写错，
实际原因是 mathtext 把 `%` 之后的内容整段丢弃，结尾的 `$` 因此变成"多余字符"。

- **改法**：把百分号移出数学片段 —— 写 `$F\geq95.0(2)$%`（不是 `\%`，也别指望 mathtext 认 `\%`）。
- 一次交付实测 7 处全部因此报错；用脚本做全局替换 `'%$' -> '$%'` 一次修完。
- 注意：**此坑只属于 matplotlib mathtext（总结框图 spec）**。`.md` 里的公式走 KaTeX，
  `\%` 是合法的（实测 137 条行内公式全通过），两种渲染器行为不同，不要混淆。

### 3.0.2 `**粗体**` 与 Unicode 上下标：matplotlib 都不解析（比 `%` 更常踩）
总结框图的 spec 是**纯文本 + `$LaTeX$`**，不支持 Markdown：
- 写 `**可扩展量子计算**` 会**原样显示星号**（实测整张图 8 处）。骨架脚本没有去星号逻辑，必须在 spec 里直接写纯文本。
- `³P₀`、`¹⁷¹Yb`、`T₂`、`10⁻¹¹`、`|0⟩` 中的 Unicode 上下标与 `⟨⟩`（U+27E8/27E9）
  **Microsoft YaHei 缺字形**，渲染成空心方框（`Glyph 8322/8310/207B/27E9 missing from font`）。
  → **一律改写为数学片段**：`$^{3}P_{0}$`、`$^{171}$Yb`、`$T_{2}$`、`$10^{-11}$`、`$|0\rangle$`。
- 收尾自检（只在 JPEG/PNG 出图前跑）：
  ```python
  import re
  outside = re.sub(r'\$[^$]*\$', '', spec_text)   # 数学片段之外
  bad = [c for c in outside if ord(c) in (0x2082,0x2080,0x2076,0x207B,0x27E9,0x27E8,
                                          0x00B2,0x00B3,0x00B9,0x2070,0x2074,0x2075)]
  ```
  应为空；同时把 spec 里每个 `$...$` 片段喂给 `ax.text()` 试解析一遍，确认无异常。

### 3.0.3 用脚本改 JSON spec 时的转义地雷（会把公式悄悄改坏）
用 Python 脚本对 JSON **字符串内容**做替换（如 `s.replace("10^4","10^{4}")` 批量补花括号）时，
若替换串里含 `\times` / `\rangle` / `\frac`，Python 写入的**裸反斜杠**会让 `json.load` 报
`Invalid \escape`；而若先做一遍 `re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', s)` 补救，
**写进去的却是字面 `\t`、`\r`、`\n`** —— 后续读取时被解释成 TAB/CR/换行，
表现为公式片段变成 `$(0.28\pm0.03)	imes10^{-11}$`（`\times` 成了 TAB + "imes"）、
`$|0angle$`（`\rangle` 成了 CR + "angle"）。
**正确做法：不要在 JSON 文本上做替换**。用 `json.load` 读出对象 → 递归修改**字符串值** → `json.dumps` 写回。
定稿前把全部 `$...$` 片段打印出来逐条核对，这几个符号肉眼极易看漏。

### 3.0 通用注意
- **验收高框图要切片**：7 层叙事出图约 15 × 24 in（实测 2340 × 3729 px），
  整张 `Read` 会被缩放成看不清字号，无法判断"末行是否溢出"。
  用 PIL 纵向切成 3 段（每段高度 ±40 px 重叠）再逐段 Read，一次即可定案。
- 中文字体：`font_manager.FontProperties(fname=r"C:\Windows\Fonts\msyh.ttc")`，粗体用 `msyhbd.ttc`。
- mathtext **不支持 `\tfrac` / `\dfrac`**，需替换成 `\frac`（脚本内已做 sanitize）。
- **matplotlib 3.11 起 `\ge` / `\le` 不再是 `\geq` / `\leq` 的别名**，会直接
  `ParseFatalException: Unknown symbol: \ge`。spec 里一律写 `\geq` / `\leq`。
- sanitize 做别名替换时**必须用正则 + 负向前瞻**：`s.replace(r"\le", r"\leq")` 会把
  `\left(` 改成 `\leqft(`、把 `\leq` 改成 `\leqq`；`\ge` 同理吃掉 `\geq`。
  正确写法：`re.sub(r"\\ge(?![qa-zA-Z])", r"\\geq", s)`、`re.sub(r"\\le(?![fqa-zA-Z])", r"\\leq", s)`。
- **`formula` 块的 `tex` 必须按数学排版**：matplotlib 只在 `$...$` 定界时才走 mathtext，
  否则把 LaTeX 源码**原样画出来**（曾出现整行显示 `\frac{H}{\hbar}=...` 的交付事故）。
  脚本已内置 `as_math()` 自动补 `$`；手写脚本时务必自己包上。
- 避免在普通文本（非数学模式）里使用 Microsoft YaHei 缺字形的符号，例如
  U+21D2 `⇒`、U+25A1 `□` 会触发 `Glyph missing from font` 警告并渲染成方框。
- **不要用字符串拼接拆开一个数学段**：
  ```python
  "$a=" "$b$"     # ✗ 拼成 $a=$b$，第二个 $ 提前闭合 → LaTeX 原样输出、文本框溢出
  ```
- 修完 spec 别用 shell 里手搓的多层转义 `re.sub` 改 JSON —— 极易把文件本身改坏
  （实测把 `\left(` 改成 `\leqft(`）。要么直接用编辑器改，要么用脚本文件而非 `python -c`。

### 3.1 坐标轴留白会把整张图的比例搞错（最隐蔽）
`plt.subplots()` 默认让绘图区只占画布 ~77%（`left=.125/right=.9/bottom=.11/top=.88`），
于是"1 个数据单位 = width×72/100 pt"这个假设**不成立**（实际约 0.77 倍），
文字相对画布被放大约 1.3 倍 → **每块文字的末行都会溢出边框**，看起来像"块高算错了"。

```python
fig = plt.figure(figsize=(w, h), dpi=150)
ax = fig.add_axes([0, 0, 1, 1])     # ✓ 绘图区铺满画布
```
建好轴后自检横纵单位是否等长：
```python
bb = ax.get_window_extent(fig.canvas.get_renderer())
ux = bb.width / 100.0 * 72.0 / fig.dpi
uy = bb.height / total * 72.0 / fig.dpi
assert abs(ux - uy) / uy < 0.01
```
> 注：早期在 `plt.subplots` 画布上实测出的"行高倍率 1.384"其实是对的（≈1.065/0.77），
> 当时误判为算错而弃用，绕了远路。**度量异常时先怀疑画布比例，不要先怀疑公式。**

### 3.2 文本度量的单位：像素 ≠ 点
`renderer.get_text_width_height_descent(s, prop, ismath)` 返回**像素**（取决于画布 dpi），
`get_window_extent()` 同样返回像素。换算成点必须乘 `72/dpi`：
```python
w_px, _, _ = renderer.get_text_width_height_descent(s, prop, False)
w_pt = w_px * 72.0 / dpi        # ← 漏掉这一步，折行宽度会差 dpi/72 倍
```
探针画布的 dpi 要与最终画布一致（都用 150），否则折行位置与渲染结果对不上。

### 3.3 行高的真实倍率（已实测，msyh 字体）
```
每行高度   = 1.0654 × 字号 × linespacing     # 与字号无关，恒定倍率
n 行文本块 = n × 1.0654 × 字号 × linespacing
```
中文黑体的 ascent/descent 远大于西文，**不能把 linespacing 直接当行高**。
稳妥做法是**运行时标定**：画 2 行 100pt 文本量高度再除以 200（脚本 `calibrate_line_factor` 已实现）。

### 3.4 中文避头尾（禁则）
贪心折行会把句号、右括号挤到下一行形成"单字孤行"（实测出现过单独一行的 `。`）。需加规则：
```python
NO_LINE_START = set("。、，．,.;:!?）)]}】》」』”’%‰…·〉")   # 不置行首，必要时悬挂
NO_LINE_END   = set("（([{【《「『“‘〈")                    # 不置行尾，随之移到下一行
```

### 3.5 块高必须按"折行后"的行数算
不能用 spec 里 `lines` 的条数——一条源文本可能折成 2–3 行，否则必然溢出。
同理，**改字号只改 `--font-scale`，不要手改各处字号常量**：脚本会按字号重算全部块高并自动重排。

### 3.6 放大字号 ≠ 放大画布
`--font-scale` 同时增大字号与块高，画布变高而宽度不变 → 每行容纳字数减少 →
**文字相对画布宽度的占比变大**，实际查看时字确实变大。
若只调 `--width` 而不动字号，显示时被缩放回去，等于没变。

**脚本默认 `--font-scale 1.35`**（正文 11.4pt→15.4pt，画布 15×18.9 in）——
这是本用户的既定偏好，默认出图即为大字号，不需要手动传参。


---

## 4. 本机环境

- **不要用 Git Bash 的系统命令**：本机 PATH 残缺，`ls` / `cat` / `tail` / `head` / `dirname` 均不可用，
  且 `|` 管道与 `> _build/x.log` 重定向到尚不存在的目录都会失败。
  → 一律用受管 Python 做文件操作，日志重定向到**已存在的**目录，或多条命令串在一个 python 调用里。
- **PowerShell 工具不回显 stdout**：`& python script.py` 的打印内容看不到（退出码正常）。
  → 脚本必须**自己把结果写进文件**，再用 Read 读取；不要指望从工具输出里拿结果。
- **PowerShell 的 `*>` 重定向写的是 UTF-16LE**：Read 会把这种文件判为二进制（"Cannot display content of binary file"）。
  → 用 Python `io.open(path, encoding="utf-16")` 转写成 UTF-8 后再读，或干脆别用 `*>`。
- 受管 Python：`C:\Users\admin\.workbuddy\binaries\python\versions\3.13.12\python.exe`
- 已建 venv：`C:\Users\admin\.workbuddy\binaries\python\envs\default`（含 pymupdf、matplotlib）
- Node 工作区：`C:\Users\admin\.workbuddy\binaries\node\workspace`（`npm install katex marked`）
  运行脚本时设 `NODE_PATH` 指向其 `node_modules`。
- 若 `node/workspace` 不存在，需先创建目录再 `npm install`（npm 不会自动建目录）。

---

## 5. 交付约定

- **只输出 `.md` + `images/`，不要主动生成 HTML 预览**（用户已明确表示不需要）。
- 中间产物（抽取脚本、原始文本、日志、`.bak`）统一收进 `_build/`，工作区根目录保持整洁：
  ```
  <workspace>/
  ├── <论文>.md
  ├── images/            # Fig00_总结框图.png + Fig01..FigNN.png
  └── _build/            # 中间产物
  ```
- 参考文献**保留原文著录格式不翻译**，只加一句"按学术惯例保留原文"。
- 原文明显笔误以「**译注**」标出，**不改动原文推理链条**。
- 头部写明版权与使用范围（原文常为 Springer 专有许可），并注明"引用以原文为准"。
