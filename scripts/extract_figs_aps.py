#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""APS / PRL 双栏版式专用裁图：`FIG.` 全大写 + 按栏切分版带。

与 extract_figs.py 的差别（见 ../references/pitfalls.md 第 2 节）：
  1. 图注正则匹配 `FIG. 1.`（大写），extract_figs.py 的 `^(Fig\\.|Figure)` 匹配不到；
  2. **按栏切分**：图注宽度 > --full-width ⇒ 通栏；否则 x0 < --col-split 判左栏，反之右栏；
     band 只在同栏内推进（否则左栏图注会截断右栏图的 band）；
  3. 横向一律取**整栏宽度**而不是图形并集 —— 轴标题、刻度、(a)(b) 都是文字块，
     不在 get_drawings() 里，用并集会把 `Ω/2π (MHz)` 这类旋转轴标题切掉。

用法:
    python extract_figs_aps.py --pdf paper.pdf --out-dir images --report figs.json
    python extract_figs_aps.py --pdf paper.pdf --out-dir images --column 52,297.1 --column 315,560.1
"""
import argparse
import json
import os
import re
import sys

import pymupdf

CAP_RE = re.compile(r'^(FIG\.|Fig\.|Figure)\s*S?(\d+)\b', re.I)


def union(rects):
    u = rects[0]
    for r in rects[1:]:
        u = u | r
    return u


def is_label(t, h, max_chars=70, max_h=34.0):
    t = t.strip()
    if not t or CAP_RE.match(t):
        return False
    return len(t) <= max_chars and h <= max_h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--report", default="")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--header-bottom", type=float, default=40.0,
                    help="页眉文字下沿；钳制图的上边界。APS 页眉 y≈27–37.6 ⇒ 40")
    ap.add_argument("--col-split", type=float, default=306.0, help="左右栏分界 x")
    ap.add_argument("--full-width", type=float, default=400.0,
                    help="图注宽度超过此值判为通栏图")
    ap.add_argument("--column", action="append", default=[],
                    help="手动指定栏的 x 范围 'x0,x1'，可重复；默认按 --col-split 自动推断")
    args = ap.parse_args()

    doc = pymupdf.open(args.pdf)
    os.makedirs(args.out_dir, exist_ok=True)

    manual = []
    for c in args.column:
        a, b = [float(v) for v in re.split(r'[,\s]+', c.strip())]
        manual.append((a, b))

    report = []
    for pno in range(doc.page_count):
        page = doc[pno]
        H, W = page.rect.height, page.rect.width
        blocks = [(b[0], b[1], b[2], b[3], b[4]) for b in page.get_text("blocks")]
        caps = [b for b in blocks if CAP_RE.match(b[4].strip())]
        if not caps:
            continue

        prims = [d["rect"] for d in page.get_drawings()
                 if d["rect"].width > 3 and d["rect"].height > 3]
        prims += [pymupdf.Rect(i["bbox"]) for i in page.get_image_info()
                  if pymupdf.Rect(i["bbox"]).width > 6
                  and pymupdf.Rect(i["bbox"]).height > 6]

        if manual:
            cols = {i: [] for i in range(len(manual))}
            for c in caps:
                best, bi = None, 0
                for i, (x0, x1) in enumerate(manual):
                    ov = min(c[2], x1) - max(c[0], x0)
                    if best is None or ov > best:
                        best, bi = ov, i
                cols[bi].append(c)
        else:
            cols = {}
            for c in caps:
                key = "full" if (c[2] - c[0]) > args.full_width else (
                    "left" if c[0] < args.col_split else "right")
                cols.setdefault(key, []).append(c)

        for key, lst in cols.items():
            if not lst:
                continue
            lst.sort(key=lambda c: c[1])
            band_top = args.header_bottom
            for k, (cx0, cy0, cx1, cy1, ctxt) in enumerate(lst):
                fig_no = int(CAP_RE.match(ctxt.strip()).group(2))
                band_bottom = lst[k + 1][1] if k + 1 < len(lst) else H - 40.0

                if manual and isinstance(key, int):
                    x0, x1 = manual[key]
                elif key == "full":
                    x0, x1 = 52.0, W - 52.0
                elif key == "left":
                    x0, x1 = 52.0, args.col_split - 9.0
                else:
                    x0, x1 = args.col_split + 9.0, W - 52.0

                inband = [r for r in prims
                          if r.y0 >= band_top - 2 and r.y1 <= band_bottom
                          and r.x1 > x0 - 2 and r.x0 < x1 + 2
                          and r.y1 <= cy0 + 1]
                if not inband:
                    report.append(dict(page=pno + 1, fig=fig_no, mode="missed"))
                    band_top = cy1
                    continue

                U = union(inband)
                for (bx0, by0, bx1, by1, bt) in blocks:
                    if not (by0 >= band_top - 6 and by1 <= cy0 + 1):
                        continue
                    if not (bx0 < x1 + 2 and bx1 > x0 - 2):
                        continue
                    if not is_label(bt, by1 - by0):
                        continue
                    U = U | pymupdf.Rect(bx0, by0, bx1, by1)

                top = max(U.y0 - 8.0, band_top + 2.0)
                clip = pymupdf.Rect(x0, top, x1, cy0 - 2.0)
                name = "Fig%02d.png" % fig_no
                pix = page.get_pixmap(matrix=pymupdf.Matrix(args.dpi / 72.0,
                                                            args.dpi / 72.0), clip=clip)
                pix.save(os.path.join(args.out_dir, name))
                report.append(dict(page=pno + 1, fig=fig_no, col=str(key), file=name,
                                   px=[pix.width, pix.height],
                                   clip=[round(v, 1) for v in clip]))
                band_top = cy1

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    print("figures written: %d" % sum(1 for r in report if r.get("file")))
    for r in report:
        print("  p%-3s Fig%-3s %-6s %s" % (r["page"], r["fig"], r.get("col", ""),
                                           r.get("file", "")))
    missed = [r for r in report if "file" not in r]
    if missed:
        print("!! 未裁出的图: %s" % missed, file=sys.stderr)


if __name__ == "__main__":
    main()
