#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从学术 PDF 中按"图注锚点 + 版带"定位插图，并把矢量区域 300 dpi 渲染为 PNG。

用法:
    python extract_figs.py --pdf paper.pdf --out-dir images
    python extract_figs.py --pdf paper.pdf --out-dir images --pages 11,12,14,35
    python extract_figs.py --pdf paper.pdf --out-dir images --dpi 400 --report figs.json

设计依据与踩坑记录见 ../references/pitfalls.md。
"""
import argparse
import json
import os
import re
import sys

import pymupdf

CAP_RE = re.compile(r'^(Fig\.|Figure)\s*(\d+)')
TAB_RE = re.compile(r'^(Table|TABLE)\s*\d+')

HEADER_BOTTOM = 52.0        # 页眉文字下沿，用于钳制上边界，防止把 running head 裁进来
TOP_PAD = 26.0              # 上留白：吸收子图标题 / (a)(b) / 坐标轴标题
SIDE_PAD = 14.0             # 左右留白
PAGE_SAFE = (22.0, 34.0)    # 页面安全区左右/上下内缩


def is_label(text, rect, max_chars=70, max_h=34.0):
    """判断一个文本块是否属于"图内标签"（可被吸收），排除图注/表题/长段落。"""
    t = text.strip()
    if not t:
        return False
    if CAP_RE.match(t) or TAB_RE.match(t):
        return False
    if len(t) > max_chars or (rect[3] - rect[1]) > max_h:
        return False
    return True


def absorb(rect, labels, gap=34.0, max_iter=8):
    """把并集矩形向外扩张，吸收邻近的短标签文本块（纵轴标题、刻度、(a)(b) 等）。"""
    changed, it = True, 0
    while changed and it < max_iter:
        changed, it = False, it + 1
        for lb in labels:
            r = pymupdf.Rect(lb[0], lb[1], lb[2], lb[3])
            # 水平方向相叠 → 允许向上/下扩张
            if min(rect.x1, r.x1) - max(rect.x0, r.x0) > -8:
                if -2.0 <= r.y1 - rect.y0 <= gap or -2.0 <= rect.y1 - r.y0 <= gap:
                    rect = rect | r
                    changed = True
                    continue
            # 垂直方向相叠 → 允许向左/右扩张
            if min(rect.y1, r.y1) - max(rect.y0, r.y0) > -8:
                if -2.0 <= r.x1 - rect.x0 <= gap or -2.0 <= r.x1 - r.x0 <= gap:
                    rect = rect | r
                    changed = True
                    continue
    return rect


def union(rects):
    u = rects[0]
    for r in rects[1:]:
        u = u | r
    return u


def scan_captions(doc, pages):
    """返回 {页码(0基): [(x0, y0, x1, y1, text), ...]}，按 y 排序。"""
    found = {}
    for pno in pages:
        page = doc[pno]
        caps = []
        for b in page.get_text("blocks"):
            # 注意：blocks 的元组顺序是 (x0, y0, x1, y1, text, ...)
            x0, y0, x1, y1, txt = b[0], b[1], b[2], b[3], b[4]
            if CAP_RE.match(txt.strip()):
                caps.append((x0, y0, x1, y1, txt))
        if caps:
            found[pno] = sorted(caps, key=lambda c: c[1])
    return found


def prims_of(page):
    """页面上的矢量图形矩形 + 内嵌位图 bbox。"""
    out = [d["rect"] for d in page.get_drawings()
           if d["rect"].width > 4 and d["rect"].height > 4]
    for info in page.get_image_info():
        r = pymupdf.Rect(info["bbox"])
        if r.width > 8 and r.height > 8:
            out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--pages", default="", help="1 基页码，逗号分隔；留空则自动扫描含图注的页")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--report", default="", help="把裁切报告写成 JSON")
    args = ap.parse_args()

    doc = pymupdf.open(args.pdf)
    os.makedirs(args.out_dir, exist_ok=True)

    if args.pages.strip():
        pages = [int(x) - 1 for x in re.split(r'[,\s]+', args.pages.strip()) if x]
    else:
        pages = list(range(doc.page_count))

    caps_by_page = scan_captions(doc, pages)

    # 统计内嵌位图数量，供判断"是否需要裁切"
    n_raster = sum(len(doc[i].get_images(full=True)) for i in pages)

    report = []
    for pno in sorted(caps_by_page):
        page = doc[pno]
        H, W = page.rect.height, page.rect.width
        area = pymupdf.Rect(PAGE_SAFE[0], PAGE_SAFE[1], W - PAGE_SAFE[0], H - PAGE_SAFE[1])

        blocks = [(b[0], b[1], b[2], b[3], b[4]) for b in page.get_text("blocks")]
        labels = [b for b in blocks if is_label(b[4], (b[0], b[1], b[2], b[3]))]
        prims = prims_of(page)

        band_top = HEADER_BOTTOM
        caps = caps_by_page[pno]
        for k, (cx0, cy0, cx1, cy1, ctxt) in enumerate(caps):
            fig_no = int(CAP_RE.match(ctxt.strip()).group(2))
            band_bottom = caps[k + 1][1] if k + 1 < len(caps) else H - 40.0

            inband = [r for r in prims if r.y0 >= band_top - 2 and r.y1 <= band_bottom]
            above = [r for r in inband if r.y1 <= cy0 + 1]

            mode, U = "normal", None
            if above:
                U = union(above)
            if U is None or (U.y0 >= cy0 - 8 and len(inband) >= 2 and inband[0].y1 > cy1 + 10):
                # 图注与插图并排：图形起始于图注同高处、且纵向远超图注
                mode = "side-by-side"
                U = union(inband) if len(inband) >= 2 else U
            if U is None:
                report.append(dict(page=pno + 1, fig=fig_no, mode="missed"))
                band_top = cy1
                continue

            U = absorb(pymupdf.Rect(U),
                       [b for b in labels if b[1] >= band_top - 6 and b[3] <= band_bottom])

            top = max(U.y0 - (12.0 if mode == "side-by-side" else TOP_PAD), band_top + 3.0)
            bottom = U.y1 + 14.0 if mode == "side-by-side" else cy0 - 2.0
            clip = pymupdf.Rect(U.x0 - SIDE_PAD, top, U.x1 + SIDE_PAD, bottom) & area

            name = "Fig%02d.png" % fig_no
            pix = page.get_pixmap(matrix=pymupdf.Matrix(args.dpi / 72.0, args.dpi / 72.0), clip=clip)
            pix.save(os.path.join(args.out_dir, name))
            report.append(dict(page=pno + 1, fig=fig_no, mode=mode, file=name,
                               px=[pix.width, pix.height],
                               clip=[round(v, 1) for v in clip]))
            band_top = cy1

    print("embedded raster images in pages scanned: %d" % n_raster)
    print("figures written: %d" % sum(1 for r in report if r.get("file")))
    for r in report:
        print("  p%-3s Fig%-3s %-12s %s" % (r["page"], r["fig"], r["mode"],
                                            r.get("file", "")))
    missed = [r for r in report if "file" not in r]
    if missed:
        print("!! 未裁出的图: %s" % missed, file=sys.stderr)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
