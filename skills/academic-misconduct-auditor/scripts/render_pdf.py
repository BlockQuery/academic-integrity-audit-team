#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把审计报告转成 PDF（Markdown 或 HTML 均可作为输入）

原理：调用本机已安装的 Chromium 内核浏览器（Edge / Chrome）无头模式打印。
不引入第三方 Python 依赖，不改动源文件，适合离线与举报场景。

用法:
  python render_pdf.py --input report.md   --output report.pdf
  python render_pdf.py --input report.html --output report.pdf
  python render_pdf.py --input report.md   --output report.pdf --title "学术成果审计报告：某某"

可选:
  --keep-html      保留中间 HTML（默认保留，名为 <output>.html）
  --paper A4|A3    纸张，默认 A4
  --landscape      横向（宽表格多的报告用）

退出码: 0 成功；1 失败（含未找到浏览器）。
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# 常见 Chromium 内核浏览器安装位置（Windows / macOS / Linux）
CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/microsoft-edge",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
]

PATH_NAMES = ["msedge", "microsoft-edge", "google-chrome", "chrome", "chromium", "chromium-browser"]


def find_browser(explicit=None):
    """按显式指定 → 常见路径 → PATH 的顺序找浏览器可执行文件。"""
    if explicit:
        p = Path(explicit)
        if p.exists():
            return str(p)
        print(f"[warn] 指定的浏览器不存在: {explicit}", file=sys.stderr)
    for c in CANDIDATES:
        if Path(c).exists():
            return c
    for n in PATH_NAMES:
        hit = shutil.which(n)
        if hit:
            return hit
    return None


def md_to_html(md_path, html_path):
    """复用同目录 render_report.py 的渲染逻辑，保持样式与 HTML 版一致。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import render_report  # noqa: WPS433
    except ImportError as e:
        raise RuntimeError(
            f"找不到 render_report.py，无法把 Markdown 转 HTML：{e}\n"
            f"请先把 md 转成 html，或确认两个脚本在同一目录。"
        ) from e

    md = Path(md_path).read_text(encoding="utf-8")
    body = render_report.convert(md)
    title = Path(md_path).stem
    doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{render_report.html.escape(title)}</title>
<style>{render_report.CSS}</style>
</head>
<body>
<div class="page">
{body}
<div class="footer">本报告基于公开学术数据生成，仅供委托方内部核查使用。不构成学术不端认定。</div>
</div>
</body>
</html>
"""
    Path(html_path).write_text(doc, encoding="utf-8")


def html_to_pdf(browser, html_path, pdf_path, paper="A4", landscape=False):
    """调用浏览器无头模式打印 PDF。"""
    url = Path(html_path).resolve().as_uri()
    out = Path(pdf_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    # 独立的临时 profile：避免与用户正在使用的浏览器实例抢锁而失败
    profile_dir = tempfile.mkdtemp(prefix="audit_pdf_profile_")
    try:
        cmd = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-extensions",
            "--no-first-run",
            "--no-default-browser-check",
            "--no-pdf-header-footer",
            f"--user-data-dir={profile_dir}",
            f"--print-to-pdf={out}",
            "--print-to-pdf-no-header",
            "--virtual-time-budget=6000",
            url,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)

        if not out.exists() or out.stat().st_size == 0:
            detail = (proc.stderr or proc.stdout or "").strip()[-800:]
            raise RuntimeError(
                f"浏览器未生成 PDF。退出码 {proc.returncode}。\n输出尾部:\n{detail}\n"
                f"（旧版 Chromium 可去掉 --headless=new 改用 --headless 重试）"
            )

        head = out.read_bytes()[:5]
        if head != b"%PDF-":
            raise RuntimeError(f"生成的文件不是合法 PDF（头部为 {head!r}），可能被重定向到了错误页面。")

        return out
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="report.md 或 report.html")
    ap.add_argument("--output", required=True, help="输出 PDF 路径")
    ap.add_argument("--title", default="", help="仅在输入为 md 且需要在 HTML 中体现时使用")
    ap.add_argument("--browser", default="", help="手动指定浏览器可执行文件路径")
    ap.add_argument("--paper", default="A4", choices=["A4", "A3", "Letter"])
    ap.add_argument("--landscape", action="store_true")
    ap.add_argument("--keep-html", action="store_true", default=True)
    args = ap.parse_args()

    src = Path(args.input).resolve()
    if not src.exists():
        print(f"[error] 输入不存在: {src}", file=sys.stderr)
        return 1

    browser = find_browser(args.browser or None)
    if not browser:
        print(
            "[error] 未找到 Edge / Chrome。请安装其一，或用 --browser 指定路径。\n"
            "        退路：把 HTML 交给用户，用浏览器 Ctrl+P 另存为 PDF。",
            file=sys.stderr,
        )
        return 1
    print(f"[info] 使用浏览器: {browser}")

    out = Path(args.output).resolve()
    tmp_html = None
    try:
        if src.suffix.lower() in (".html", ".htm"):
            html_path = src
        else:
            tmp_html = out.with_suffix(".html")
            md_to_html(src, tmp_html)
            html_path = tmp_html
            print(f"[ok] Markdown -> HTML: {tmp_html}")

        pdf = html_to_pdf(browser, html_path, out, args.paper, args.landscape)
        size_kb = pdf.stat().st_size / 1024
        print(f"[ok] PDF -> {pdf}  ({size_kb:.1f} KB)")
        if not args.keep_html and tmp_html and tmp_html.exists():
            tmp_html.unlink()
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[error] {e}", file=sys.stderr)
        if tmp_html and tmp_html.exists():
            print(f"[hint] HTML 已保留，可手动打印为 PDF: {tmp_html}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
