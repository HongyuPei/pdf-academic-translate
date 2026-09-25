#!/usr/bin/env node
/**
 * 交付前用 KaTeX 逐条编译 .md 里的公式，比肉眼可靠得多。
 *
 * 用法（需先在本机 node workspace 里 `npm install katex`）：
 *   NODE_PATH=C:/Users/admin/.workbuddy/binaries/node/workspace/node_modules \
 *   C:/Users/admin/.workbuddy/binaries/node/versions/22.22.2-3/node.exe \
 *     check_math.js --md paper_zh.md
 *
 * 同时做一次"对照实验"：把行间公式当 inline 渲染，用于复现/确认
 * "单行 $$...$$ 导致 \tag 报错" 这一经典故障。
 */
const fs = require('fs');

function arg(name, dflt) {
  const i = process.argv.indexOf('--' + name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : dflt;
}

const MD = arg('md');
if (!MD) {
  console.error('usage: check_math.js --md <file.md> [--katex <module>]');
  process.exit(2);
}

const katex = require(arg('katex', 'katex'));

const lines = fs.readFileSync(MD, 'utf8').split('\n');

// ---- 收集独占行的 $$...$$ 行间公式 ----
const blocks = [];
let inFence = false;
for (let i = 0; i < lines.length; i++) {
  const st = lines[i].trim();
  if (st.startsWith('```')) { inFence = !inFence; continue; }
  if (!inFence && st === '$$') {
    const buf = [];
    let j = i + 1;
    while (j < lines.length && lines[j].trim() !== '$$') buf.push(lines[j++]);
    blocks.push({ line: i + 1, tex: buf.join('\n') });
    i = j;
  }
}

// ---- 收集行内 $...$（跳过围栏与反引号代码）----
const inlines = [];
const singleLineBlocks = [];
inFence = false;
lines.forEach((l, idx) => {
  if (l.trim().startsWith('```')) { inFence = !inFence; return; }
  if (inFence) return;
  const stripped = l.replace(/`[^`]*`/g, m => ' '.repeat(m.length));
  if (/^\s*\$\$.+\$\$\s*$/.test(stripped)) singleLineBlocks.push(idx + 1);
  const re = /\$([^$\n]+)\$/g;
  let m;
  while ((m = re.exec(stripped)) !== null) inlines.push({ line: idx + 1, tex: m[1] });
});

function test(list, displayMode, label) {
  let ok = 0;
  const bad = [];
  for (const it of list) {
    try {
      katex.renderToString(it.tex, { displayMode, throwOnError: true, strict: false });
      ok++;
    } catch (e) {
      bad.push({ line: it.line, msg: String(e.message).split('\n')[0], tex: it.tex.slice(0, 110) });
    }
  }
  console.log(`\n=== ${label}: 共 ${list.length} 条，通过 ${ok}，失败 ${bad.length} ===`);
  bad.forEach(b => console.log(`  L${b.line}  ${b.msg}\n        ${b.tex}`));
  return bad.length;
}

const f1 = test(blocks, true, '行间公式 (displayMode=true)');
const f2 = test(inlines, false, '行内公式 (displayMode=false)');

console.log('\n=== 结构性自检 ===');
console.log(`  单行 $$...$$ 残留行 : ${singleLineBlocks.length} ${singleLineBlocks.slice(0, 10)}`);
const odd = lines.map((l, i) => [i + 1, l])
  .filter(([, l]) => (l.match(/\$/g) || []).length % 2 === 1)
  .map(([i]) => i);
console.log(`  '$' 个数为奇数的行  : ${odd.length} ${odd.slice(0, 10)}`);
const tagged = blocks.filter(b => /\\tag\{/.test(b.tex)).length;
console.log(`  行间公式中带 \\tag{} : ${tagged}`);

if (tagged > 0) {
  let fails = 0;
  for (const it of blocks) {
    try { katex.renderToString(it.tex, { displayMode: false, throwOnError: true, strict: false }); }
    catch (e) { fails++; }
  }
  console.log(`  [对照] 这些行间公式若按 inline 渲染，失败 ${fails}/${blocks.length}`
    + `（>0 正说明"必须写成独立行块形式"）`);
}

const total = f1 + f2 + singleLineBlocks.length + odd.length;
console.log('\n' + (total === 0 ? 'ALL CHECKS PASSED' : `FAILED: ${total} problem(s)`));
process.exit(total === 0 ? 0 : 1);
