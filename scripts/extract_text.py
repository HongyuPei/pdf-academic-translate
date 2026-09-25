#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 PDF 正文抽取为带页码标记的纯文本，供逐段阅读与翻译。

用法:
    python extract_text.py --pdf paper.pdf --out raw_text.txt
    python extract_text.py --pdf paper.pdf --out raw_text.txt --blocks   # 带块坐标，便于定位图表
"""
import argparse
import sys

import pymupdf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--blocks", action="store_true",
                    help="按文本块输出并附带 bbox，便于定位图表位置")
    args = ap.parse_args()

    doc = pymupdf.open(args.pdf)
    chunks = []
    total = 0
    for i, page in enumerate(doc):
        chunks.append("===== PAGE %d =====" % (i + 1))
        if args.blocks:
            for b in page.get_text("blocks"):
                # blocks 元组顺序：(x0, y0, x1, y1, text, block_no, block_type)
                chunks.append("[x %.0f-%.0f y %.1f-%.1f] %s"
                              % (b[0], b[2], b[1], b[3], b[4].strip().replace("\n", " ")))
        else:
            chunks.append(page.get_text("text"))
        total += len(chunks[-1])

    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(chunks))

    print("pages : %d" % doc.page_count)
    print("chars : %d" % total)
    print("written: %s" % args.out)
    # 顺带告知是否含内嵌位图，决定配图是否只能靠裁切
    n = sum(len(page.get_images(full=True)) for page in doc)
    print("embedded raster images: %d%s"
          % (n, "  -> 插图均为矢量，配图须用 extract_figs.py 区域渲染" if n == 0 else ""))


if __name__ == "__main__":
    main()
