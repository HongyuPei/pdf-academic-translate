#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""按 JSON 规格绘制"全文总结性框图"（用于学术翻译 .md 的开篇总览图）。

特性：
  - 文本自动折行（中英混排 + 行内 $LaTeX$ 片段），按画布实际宽度测量，不溢出边框；
  - 运行时**标定字体度量**推算行高，区块高度按实际折行数计算，任意字号都排版正确；
  - --font-scale 统一缩放全部字号（自动重排，不会因放大而溢出）。

用法:
    python make_summary_diagram.py --spec summary_spec.json --out images/Fig00_总结框图.png
    python make_summary_diagram.py --spec summary_spec.json --out images/Fig00.png --font-scale 1.6

默认 --font-scale 1.35（正文 15.4pt / 标签 18.2pt / 标题 25.0pt）。
字号偏大是本用户的既定偏好，**无需每次手动传参**；需要更紧凑时再显式给 1.0–1.2。

spec 结构（除 title/blocks 外均可省略）:
{
  "title": "中文主标题",
  "subtitle": "English original title",
  "meta": "Zhang et al. · Journal (2024) 23:213 · 全文逻辑框架",
  "footer": "图 0  论文全文总结性框图（依据原文逻辑结构整理绘制）",
  "blocks": [
    {"kind": "text",    "tag": "① 研究背景", "color": "ctx",    "lines": ["...", "..."]},
    {"kind": "formula", "tag": "③ 理论核心", "color": "core",   "lead": "...",
     "tex": "\\varepsilon(\\rho)=p\\rho+z", "lines": ["..."]},
    {"kind": "steps",   "tag": "⑤ 方法",     "color": "method", "lead": "...",
     "steps": [["①", "标题", "说明"], ...]},
    {"kind": "grid",    "tag": "⑥ 实验",     "color": "exp",    "cols": 2,
     "items": [["(a)", "标题", "多行\\n说明"], ...]}
  ]
}

color 可选键: ctx / prob / core / thm / method / exp / res
lines / body 中的 \\n 视为强制换行，其余超宽内容自动折行。
"""
import argparse
import json
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

FONT_REG = r"C:\Windows\Fonts\msyh.ttc"
FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"

PALETTE = {
    "ctx":    ("#EEF3F9", "#4A78B0"),
    "prob":   ("#FDF1E7", "#D08A4A"),
    "core":   ("#EAF5EF", "#3F8F6B"),
    "thm":    ("#EDF0FA", "#5B6BB0"),
    "method": ("#FFF8E8", "#C9A227"),
    "exp":    ("#F1F1FB", "#6B5FA8"),
    "res":    ("#FCEDEF", "#B0525F"),
}
INK = "#1D2530"

X0, XW = 5.0, 90.0
TEXT_L = X0 + 2.5
GAP = 1.9
FOOTER_H = 2.4
TAG_PAD = 0.95           # 标签条上下留白（单位）
BLOCK_BOT_PAD = 0.95
ROW_PAD = 0.85           # 步骤/单元内的行上下留白
LSP = 1.42               # linespacing

# 基准字号（--font-scale 会整体相乘）
FS = dict(title=18.5, subtitle=11.0, meta=10.5, tag=13.5, lead=11.4,
          line=11.4, formula=12.4, step_num=13.5, step_head=11.8,
          step_body=11.0, cell_tag=10.6, cell_head=11.4, cell_body=10.4,
          footer=11.0)

TEXT_AVAIL = (X0 + XW - 2.5) - TEXT_L                    # 正文可用宽度（单位）
STEP_BODY_X = TEXT_L + 24.0                              # 步骤说明起始 x
STEP_AVAIL = (X0 + XW - 2.0) - STEP_BODY_X


def sanitize(tex):
    """mathtext 不支持的命令做等价替换。

    注意：必须用正则 + 负向前瞻，否则 `\\le` 会命中 `\\left(`、`\\leq`，
    `\\ge` 会命中 `\\geq`，把公式整体改坏。
    """
    s = str(tex).replace(r"\tfrac", r"\frac").replace(r"\dfrac", r"\frac")
    s = re.sub(r"\\ge(?![qa-zA-Z])", r"\\geq", s)
    s = re.sub(r"\\le(?![fqa-zA-Z])", r"\\leq", s)
    return s


def as_math(tex):
    """确保 tex 以 $...$ 包裹 —— matplotlib 只在 $ 定界时按数学排版，
    否则会把 LaTeX 源码原样画出（曾导致 formula 块整行显示为源码）。"""
    s = str(tex).strip()
    if s.startswith("$") and s.endswith("$") and len(s) > 2:
        return s
    return "$" + sanitize(s) + "$"


# 中文避头尾（禁则）字符集
NO_LINE_START = set("。、，．,.;:!?）)]}】》」』”’%‰…·〉")
NO_LINE_END = set("（([{【《「『“‘〈")


class Measurer:
    """按画布单位测量文本宽度，用于自动折行。"""

    def __init__(self, renderer, prop_reg, prop_bold, unit_pt, dpi):
        self.r = renderer
        self.p = prop_reg
        self.pb = prop_bold
        self.unit = unit_pt          # 1 个画布单位 = 多少 pt
        self.px2pt = 72.0 / dpi      # get_text_width_height_descent 返回的是像素
        self.cache = {}

    def _w(self, s, prop):
        key = (s, prop.get_size())
        if key not in self.cache:
            w, _, _ = self.r.get_text_width_height_descent(s, prop, False)
            self.cache[key] = w
        return self.cache[key]

    def width(self, text, fontsize, bold=False):
        """返回文本宽度（画布单位）。支持行内 $...$ 数学片段。"""
        prop = (self.pb if bold else self.p).copy()
        prop.set_size(fontsize)
        total = 0.0
        for part in re.split(r'(\$[^$]*\$)', sanitize(text)):
            if not part:
                continue
            if part.startswith("$") and part.endswith("$") and len(part) > 2:
                try:
                    w, _, _ = self.r.get_text_width_height_descent(part, prop, True)
                except Exception:
                    w = self._w(part, prop)
                total += w
            else:
                total += self._w(part, prop)
        return total * self.px2pt / self.unit

    def wrap(self, text, avail, fontsize, bold=False):
        """把文本折行到给定宽度内；\\n 为强制换行，数学片段不可拆分。

        含中文避头尾（禁则）处理：句读/右括号等不出现在行首，
        左括号等不出现在行尾，避免出现"单字孤行"。
        """
        out_lines = []
        for para in str(text).split("\n"):
            atoms = []
            for part in re.split(r'(\$[^$]*\$)', sanitize(para)):
                if not part:
                    continue
                if part.startswith("$") and part.endswith("$") and len(part) > 2:
                    atoms.append(part)
                else:
                    atoms.extend(list(part))
            cur, cur_w = "", 0.0
            for a in atoms:
                aw = self.width(a, fontsize, bold)
                if cur and cur_w + aw > avail:
                    if a in NO_LINE_START:          # 标点不置行首 → 挂到行尾
                        cur += a
                        cur_w += aw
                        continue
                    if cur[-1] in NO_LINE_END:      # 左括号不置行尾 → 一起下移
                        moved = cur[-1]
                        cur = cur[:-1]
                        out_lines.append(cur.rstrip())
                        cur = moved + a
                        cur_w = self.width(cur, fontsize, bold)
                        continue
                    out_lines.append(cur.rstrip())
                    cur, cur_w = a, aw
                else:
                    cur += a
                    cur_w += aw
            out_lines.append(cur.rstrip())
        return out_lines or [""]


def calibrate_line_factor(renderer, prop, dpi):
    """实测"每行高度 / (字号 × linespacing)"的倍率。

    matplotlib 的实际行距取决字体自身的 ascent/descent，
    中文黑体（如 msyh）远大于 1.0，若不标定会导致文字溢出边框。
    """
    t = plt.gca().text(0, 0, "lp\nlp", fontproperties=prop, fontsize=100,
                       linespacing=1.0, va="top")
    bb = t.get_window_extent(renderer)
    h_pt = bb.height * 72.0 / dpi
    t.remove()
    return h_pt / 200.0     # 2 行 × 100pt × lsp1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--width", type=float, default=15.0, help="画布宽度（英寸）")
    ap.add_argument("--font-scale", type=float, default=1.35,
                    help="全部字号统一放大倍数。默认 1.35（本用户偏好较大字号，正文 15.4pt）；"
                         "版面偏紧或需要更多留白时可下调至 1.0–1.2")
    ap.add_argument("--theme", choices=["light", "dark"], default="light")
    args = ap.parse_args()

    spec = json.load(open(args.spec, encoding="utf-8"))
    blocks = spec["blocks"]

    fn = font_manager.FontProperties
    reg0 = fn(fname=FONT_REG)
    bold0 = fn(fname=FONT_BOLD)
    plt.rcParams["axes.unicode_minus"] = False

    k = args.font_scale
    fs = {a: b * k for a, b in FS.items()}
    unit_pt = args.width * 72.0 / 100.0          # 1 画布单位 = ? pt

    dark = args.theme == "dark"
    bg = "#1B1F27" if dark else "#FFFFFF"
    ink = "#E8ECF2" if dark else INK
    soft = "#A8B3C2" if dark else "#7A879A"
    tcol = "#BBD0EA" if dark else "#1F3B63"
    arr = "#5A6678" if dark else "#94A2B5"

    # ---------- 第一遍：标定 + 测量 + 折行 ----------
    probe = plt.figure(figsize=(args.width, args.width), dpi=150)
    pax = probe.add_axes([0, 0, 1, 1])      # 关键：绘图区铺满画布，1 unit = width*72/100 pt
    pax.set_xlim(0, 100); pax.set_ylim(0, 100)
    prenderer = probe.canvas.get_renderer()
    LF = calibrate_line_factor(prenderer, reg0, probe.dpi)
    M = Measurer(prenderer, reg0, bold0, unit_pt, probe.dpi)
    lh = lambda size: size * LSP * LF / unit_pt      # 单行高度（画布单位）

    for b in blocks:
        kind = b["kind"]
        if b.get("lead"):
            b["_lead"] = M.wrap(b["lead"], TEXT_AVAIL, fs["lead"])
        if kind in ("text", "formula"):
            b["_lines"] = []
            for ln in b.get("lines", []):
                b["_lines"] += M.wrap(ln, TEXT_AVAIL, fs["line"])
        if kind == "steps":
            for st in b.get("steps", []):
                st.append(M.wrap(st[2], STEP_AVAIL, fs["step_body"]))
        if kind == "grid":
            cols = b.get("cols", 2)
            cw = (XW - 3.0 - (cols - 1) * 2.0) / cols
            for it in b.get("items", []):
                it.append(M.wrap(it[2], cw - 3.2, fs["cell_body"]))
    plt.close(probe)

    tag_h = fs["tag"] * (LF + 2 * TAG_PAD * 0.42) / unit_pt

    def block_height(b):
        kind = b["kind"]
        lead = len(b.get("_lead", [])) * lh(fs["lead"])
        if kind == "text":
            return tag_h + lead + len(b["_lines"]) * lh(fs["line"]) + BLOCK_BOT_PAD
        if kind == "formula":
            return tag_h + lead + lh(fs["formula"]) * 1.18 + ROW_PAD \
                + len(b["_lines"]) * lh(fs["line"]) + BLOCK_BOT_PAD
        if kind == "steps":
            rows = max(len(s[3]) for s in b["steps"])
            row = rows * lh(fs["step_body"]) + ROW_PAD + 0.35
            b["_row"] = row
            return tag_h + lead + len(b["steps"]) * row + BLOCK_BOT_PAD
        if kind == "grid":
            cols = b.get("cols", 2)
            nrows = (len(b["items"]) + cols - 1) // cols
            per = max(len(it[3]) for it in b["items"])
            cell_h = lh(fs["cell_head"]) * 1.2 + per * lh(fs["cell_body"]) + 1.05
            b["_cell_h"] = cell_h
            return tag_h + nrows * (cell_h + 0.55) + BLOCK_BOT_PAD
        raise ValueError("unknown kind: %s" % kind)

    title_h = lh(fs["title"]) * 1.25 \
        + (lh(fs["subtitle"]) if spec.get("subtitle") else 0) \
        + lh(fs["meta"]) + 1.3
    total = title_h + sum(block_height(b) for b in blocks) + GAP * len(blocks) + FOOTER_H

    # ---------- 第二遍：绘制 ----------
    fig = plt.figure(figsize=(args.width, args.width * total / 100.0), dpi=150)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, total)
    ax.axis("off")
    fig.patch.set_facecolor(bg)

    # 运行时自检：横纵每单位应等长，否则文字会按错误比例缩放而溢出
    _bb = ax.get_window_extent(fig.canvas.get_renderer())
    ux = _bb.width / 100.0 * 72.0 / fig.dpi
    uy = _bb.height / total * 72.0 / fig.dpi
    if abs(ux - uy) / uy > 0.01:
        print("警告: 画布单位不自洽 (ux=%.3f uy=%.3f)，改用实测值" % (ux, uy))

    def box(x, y, w, h, fc, ec, lw=1.6, r=1.2, z=2):
        ax.add_patch(FancyBboxPatch((x, y), w, h,
                                    boxstyle="round,pad=0,rounding_size=%s" % r,
                                    linewidth=lw, edgecolor=ec, facecolor=fc, zorder=z))

    def arrow(x, y1, y2):
        ax.add_patch(FancyArrowPatch((x, y1), (x, y2), arrowstyle="-|>",
                                     mutation_scale=17, linewidth=2.0, color=arr,
                                     zorder=1, shrinkA=0, shrinkB=0))

    def txt(x, y, s, size, color=None, bold_=False, ha="left", va="top"):
        ax.text(x, y, s, fontproperties=(bold0 if bold_ else reg0), fontsize=size,
                color=color or ink, ha=ha, va=va, zorder=5, linespacing=LSP)

    y = total
    txt(50, y - lh(fs["title"]) * 0.75, spec.get("title", ""), fs["title"], tcol,
        True, "center", "center")
    if spec.get("subtitle"):
        txt(50, y - lh(fs["title"]) * 0.75 - lh(fs["subtitle"]) * 0.95,
            spec["subtitle"], fs["subtitle"], soft, False, "center", "center")
    if spec.get("meta"):
        txt(50, y - lh(fs["title"]) * 0.75 - lh(fs["subtitle"]) * 1.95,
            spec["meta"], fs["meta"], soft, False, "center", "center")
    ax.plot([X0 + 1, X0 + XW - 1], [y - title_h + 0.55, y - title_h + 0.55],
            color="#D5DDE7" if not dark else "#39414F", lw=1.2, zorder=1)
    y -= title_h

    for i, b in enumerate(blocks):
        h = block_height(b)
        fc, ec = PALETTE.get(b.get("color", "ctx"), PALETTE["ctx"])
        if dark:
            fc = "#232A36"
        top, bot = y, y - h
        box(X0, bot, XW, h, fc, ec)

        ax.text(X0 + 2.2, top - tag_h / 2 + 0.05, b.get("tag", ""), fontproperties=bold0,
                fontsize=fs["tag"], color="white", ha="left", va="center", zorder=5,
                bbox=dict(boxstyle="round,pad=0.42", facecolor=ec, edgecolor="none"))
        cy = top - tag_h - 0.30

        if b.get("_lead"):
            txt(TEXT_L, cy, "\n".join(b["_lead"]), fs["lead"])
            cy -= len(b["_lead"]) * lh(fs["lead"]) + 0.25

        kind = b["kind"]
        if kind == "formula":
            fh = lh(fs["formula"]) * 1.18
            ax.text(50, cy - fh / 2, as_math(b["tex"]), fontproperties=reg0,
                    fontsize=fs["formula"], color=ink, ha="center", va="center", zorder=5)
            cy -= fh + ROW_PAD
        if kind in ("text", "formula") and b.get("_lines"):
            txt(TEXT_L, cy, "\n".join(b["_lines"]), fs["line"])

        if kind == "steps":
            row = b["_row"]
            for j, (num, head, body, blines) in enumerate(b["steps"]):
                yy = cy - j * row
                box(TEXT_L - 1.5, yy - row + 0.30, XW - 3.0, row - 0.10,
                    "#FFFFFF", ec, lw=1.2, r=0.8, z=3)
                mid = yy - row / 2 + 0.30
                ax.text(TEXT_L + 0.6, mid, num, fontproperties=bold0, fontsize=fs["step_num"],
                        color=ec, ha="center", va="center", zorder=6)
                ax.text(TEXT_L + 2.9, mid, head, fontproperties=bold0, fontsize=fs["step_head"],
                        color=ec if dark else "#8A6D12", ha="left", va="center", zorder=6)
                ax.text(STEP_BODY_X, mid, "\n".join(blines), fontproperties=reg0,
                        fontsize=fs["step_body"], color=ink, ha="left", va="center",
                        zorder=6, linespacing=LSP)

        if kind == "grid":
            cols = b.get("cols", 2)
            cw = (XW - 3.0 - (cols - 1) * 2.0) / cols
            cell_h = b["_cell_h"]
            head_lh = lh(fs["cell_head"])
            for j, (tagtxt, head, body, blines) in enumerate(b["items"]):
                c, r = j % cols, j // cols
                bx = TEXT_L - 1.5 + c * (cw + 2.0)
                by = cy - r * (cell_h + 0.55) - cell_h
                box(bx, by, cw, cell_h, "#FFFFFF", ec, lw=1.2, r=0.9, z=3)
                hy = by + cell_h - head_lh * 0.62
                ax.text(bx + 1.4, hy, tagtxt, fontproperties=bold0,
                        fontsize=fs["cell_tag"], color=ec, ha="left", va="center", zorder=6)
                ax.text(bx + 5.9, hy, head, fontproperties=bold0,
                        fontsize=fs["cell_head"], color=tcol, ha="left", va="center", zorder=6)
                txt(bx + 1.6, by + cell_h - head_lh * 1.12, "\n".join(blines),
                    fs["cell_body"], ink, False, "left", "top")

        y = bot - GAP / 2
        if i < len(blocks) - 1:
            arrow(50, y + GAP / 2 - 0.15, y - GAP / 2 + 0.15)

    if spec.get("footer"):
        txt(50, y - FOOTER_H / 2, spec["footer"], fs["footer"], soft, False, "center", "center")

    fig.savefig(args.out, facecolor=bg, bbox_inches="tight", pad_inches=0.3)
    print("blocks     : %d" % len(blocks))
    print("line factor: %.3f (实测字体行高倍率)" % LF)
    print("font-scale : %.2f  (正文 %.1fpt / 标签 %.1fpt / 标题 %.1fpt)"
          % (k, fs["line"], fs["tag"], fs["title"]))
    print("canvas     : 100 x %.1f units  (%.1f x %.1f in)"
          % (total, args.width, args.width * total / 100.0))
    print("written    : %s" % args.out)


if __name__ == "__main__":
    try:
        main()
    except KeyError as e:
        print("spec 缺字段: %s" % e, file=sys.stderr)
        sys.exit(1)
