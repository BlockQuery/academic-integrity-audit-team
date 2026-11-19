#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 Markdown 审计报告渲染为单文件 HTML（纯标准库，无依赖）

用法:
  python render_report.py --input report.md --output report.html
  python render_report.py --input report.md --title "审计报告" --output out.html

支持: 标题 h1-h4、表格（含对齐与首行表头）、有序/无序列表、代码块、
      行内代码、粗体、斜体、引用块、水平线、段落、链接。
设计: 浅色主题、A4 打印友好、表格自动横向滚动。
"""

import argparse
import html
import re

CSS = """
:root{--ink:#1a1a1a;--muted:#666;--line:#e2e2e2;--accent:#8b1a1a;--bg:#fff;--soft:#f7f6f4;}
*{box-sizing:border-box}
body{margin:0;background:var(--soft);color:var(--ink);
 font:16px/1.75 -apple-system,"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif;}
.page{max-width:960px;margin:0 auto;background:var(--bg);padding:56px 64px 80px;
 box-shadow:0 1px 3px rgba(0,0,0,.06);}
h1{font-size:27px;line-height:1.35;margin:0 0 8px;padding-bottom:14px;
 border-bottom:3px solid var(--accent);font-weight:700;letter-spacing:-.2px}
h2{font-size:20px;margin:44px 0 14px;padding-left:11px;border-left:4px solid var(--accent);font-weight:700}
h3{font-size:17px;margin:30px 0 10px;font-weight:700}
h4{font-size:15px;margin:22px 0 8px;font-weight:700;color:var(--muted)}
p{margin:10px 0}
strong{font-weight:700}
em{font-style:normal;color:var(--muted)}
a{color:#0b5fa5;text-decoration:none;border-bottom:1px solid #cfe0ef}
a:hover{border-bottom-color:#0b5fa5}
code{background:#f2f0ed;padding:1px 5px;border-radius:3px;font-size:.9em;
 font-family:ui-monospace,Consolas,"Courier New",monospace}
pre{background:#f8f7f5;border:1px solid var(--line);border-radius:5px;padding:14px 16px;
 overflow-x:auto;font-size:13px;line-height:1.6}
pre code{background:none;padding:0}
blockquote{margin:14px 0;padding:12px 18px;background:#faf9f7;border-left:3px solid #c9c2b8;
 color:#444;font-size:14.5px}
blockquote p{margin:6px 0}
ul,ol{margin:10px 0;padding-left:26px}
li{margin:5px 0}
hr{border:0;border-top:1px solid var(--line);margin:34px 0}
.table-wrap{overflow-x:auto;margin:16px 0;border:1px solid var(--line);border-radius:5px}
table{border-collapse:collapse;width:100%;font-size:14px;background:#fff}
th,td{padding:9px 13px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
th{background:#f5f3f0;font-weight:700;white-space:nowrap;font-size:13px;
 border-bottom:2px solid #ddd8d2}
tr:last-child td{border-bottom:0}
tbody tr:hover{background:#fcfbf9}
.footer{margin-top:56px;padding-top:16px;border-top:1px solid var(--line);
 color:#999;font-size:12.5px}
@media print{
 body{background:#fff}
 .page{box-shadow:none;padding:0;max-width:none}
 h2,h3{page-break-after:avoid}
 table,pre,blockquote{page-break-inside:avoid}
 @page{margin:18mm}
}
@media (max-width:700px){.page{padding:28px 20px 48px}h1{font-size:22px}}
"""


def inline(t):
    t = html.escape(t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", t)
    return t


def split_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def is_sep(line):
    s = line.strip()
    if not s.startswith("|"):
        return False
    return bool(re.fullmatch(r"\|?[\s:|-]+\|?", s)) and "-" in s


def convert(md):
    lines = md.replace("\r\n", "\n").split("\n")
    out, i, n = [], 0, len(lines)
    while i < n:
        line = lines[i]
        raw = line.rstrip()

        if not raw.strip():
            i += 1
            continue

        # 代码块
        if raw.strip().startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + html.escape("\n".join(buf)) + "</code></pre>")
            continue

        # 水平线
        if re.fullmatch(r"\s*([-*_])\s*\1\s*\1[\s\-*_]*", raw):
            out.append("<hr>")
            i += 1
            continue

        # 标题
        m = re.match(r"^(#{1,4})\s+(.*)$", raw)
        if m:
            lv = len(m.group(1))
            out.append(f"<h{lv}>{inline(m.group(2).strip())}</h{lv}>")
            i += 1
            continue

        # 表格
        if raw.strip().startswith("|") and i + 1 < n and is_sep(lines[i + 1]):
            header = split_row(raw)
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i]))
                i += 1
            t = ['<div class="table-wrap"><table><thead><tr>']
            t += [f"<th>{inline(c)}</th>" for c in header]
            t.append("</tr></thead><tbody>")
            for r in rows:
                r = (r + [""] * len(header))[: len(header)]
                t.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            t.append("</tbody></table></div>")
            out.append("".join(t))
            continue

        # 引用块
        if raw.lstrip().startswith(">"):
            buf = []
            while i < n and lines[i].lstrip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            inner = "<br>".join(inline(b) if b.strip() else "" for b in buf)
            out.append(f"<blockquote><p>{inner}</p></blockquote>")
            continue

        # 有序列表
        if re.match(r"^\s*\d+[.)]\s+", raw):
            buf = []
            while i < n and re.match(r"^\s*\d+[.)]\s+", lines[i]):
                item = re.sub(r"^\s*\d+[.)]\s+", "", lines[i])
                buf.append(f"<li>{inline(item)}</li>")
                i += 1
            out.append("<ol>" + "".join(buf) + "</ol>")
            continue

        # 无序列表
        if re.match(r"^\s*[-*+]\s+", raw):
            buf = []
            while i < n and re.match(r"^\s*[-*+]\s+", lines[i]):
                item = re.sub(r"^\s*[-*+]\s+", "", lines[i])
                if re.fullmatch(r"\s*[-*_]\s*", item):
                    i += 1
                    continue
                buf.append(f"<li>{inline(item)}</li>")
                i += 1
            out.append("<ul>" + "".join(buf) + "</ul>")
            continue

        # 段落
        buf = [raw.strip()]
        i += 1
        while i < n and lines[i].strip() and not re.match(
            r"^(#{1,4}\s|```|\s*[-*+]\s|\s*\d+[.)]\s|>|\|)", lines[i]
        ):
            buf.append(lines[i].strip())
            i += 1
        out.append("<p>" + inline(" ".join(buf)) + "</p>")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--title", default="学术成果审计报告")
    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        md = f.read()

    body = convert(md)
    doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(args.title)}</title>
<style>{CSS}</style>
</head>
<body>
<div class="page">
{body}
<div class="footer">本报告基于公开学术数据生成，仅供委托方内部核查使用。不构成学术不端认定。</div>
</div>
</body>
</html>
"""
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"HTML -> {args.output}")


if __name__ == "__main__":
    main()
