#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 .md 里"单行 $$公式$$"的行间公式改写成标准的三行块形式。

为什么必须改：多数 Markdown 渲染器只把 **独占一行** 的 `$$` 识别为 display 公式；
`$$公式 \tag{18}$$` 写在一行时会被当成 **行内** 公式，而 KaTeX 的 `\tag{}` 仅允许
display 模式 → 整条公式渲染失败，渲染器回退成显示 LaTeX 源码。

用法:
    python fix_math_blocks.py --md paper_zh.md            # 就地改写，先备份 .bak
    python fix_math_blocks.py --md paper_zh.md --dry-run  # 只报告不改写
"""
import argparse
import io
import os
import re
import shutil


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = io.open(args.md, encoding="utf-8").read().split("\n")
    out, converted, in_fence, leftover = [], 0, False, []

    for line in src:
        st = line.strip()

        if st.startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue

        if (not in_fence) and st.startswith("$$") and st.endswith("$$") and len(st) > 4:
            body = st[2:-2].strip()
            if body:
                if out and out[-1].strip() != "":
                    out.append("")
                out += ["$$", body, "$$", ""]
                converted += 1
                continue

        if (not in_fence) and "$$" in st and st != "$$":
            leftover.append(st[:100])

        out.append(line)

    # 折叠多余空行
    final, blanks = [], 0
    for l in out:
        if l.strip() == "":
            blanks += 1
            if blanks > 2:
                continue
        else:
            blanks = 0
        final.append(l)

    # 行内 $ 奇偶自检：奇数说明定界符未闭合，会污染后续整段
    odd = [i + 1 for i, l in enumerate(final) if l.count("$") % 2 == 1]

    print("converted single-line $$...$$ blocks : %d" % converted)
    print("remaining lines containing $$       : %d" % len(leftover))
    for l in leftover[:10]:
        print("   ", l)
    print("lines with odd number of '$'        : %d %s" % (len(odd), odd[:10] or ""))

    if args.dry_run:
        print("\n[dry-run] 未写入文件")
        return

    if converted == 0:
        print("\n无需改动。")
        return

    shutil.copyfile(args.md, args.md + ".bak")
    io.open(args.md, "w", encoding="utf-8", newline="\n").write("\n".join(final))
    print("\n已写入 %s（备份 %s.bak）" % (args.md, os.path.basename(args.md)))


if __name__ == "__main__":
    main()
