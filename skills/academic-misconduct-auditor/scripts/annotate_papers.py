#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐篇生成审计批注单，可选在 PDF 首页插入一页审计批注页

用法:
  python annotate_papers.py --works works.json --metrics metrics.json --fulltext fulltext --out annotations
  python annotate_papers.py --works works.json --metrics metrics.json --fulltext fulltext --out annotations --stamp

输出:
  <out>/<stem>.md        逐篇批注单（事实层由脚本填，判断层留给审计人）
  <out>/index.md         批注索引表（标出需重点核查的篇目）
  若传 --stamp 且有全文：在 PDF 首页插入一页审计批注页（不覆盖原文，可打印手写）

设计说明:
  脚本只写"可核实的事实"与"待核清单"，不写"是否可疑"。
  判断必须由审计人看到原文、比对图表后再填，避免元数据自动定罪。
"""

import argparse
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CHECK_ITEMS = [
    "专业相关性：主题是否落在本人研究主线内",
    "期刊质量：收录状态、预警名单、APC 与审稿周期",
    "作者位次：是否为实质贡献（一作/通讯）或参与署名",
    "基金标注：批准号真实性、负责人、依托单位、执行期覆盖",
    "数据与图片：图件跨论文复用、样本量与统计一致性",
    "伦理与注册：伦理批号、临床试验注册号是否可核",
    "重复发表：是否存在同内容中英文双发或一稿多投",
]

# 优先嵌入系统 CJK 字体（字形与字距正常），失败回退 pymupdf 内置 china-s
CJK_FONTS = [
    ("C:/Windows/Fonts/msyh.ttc", "auditcjk"),
    ("C:/Windows/Fonts/simhei.ttf", "auditcjk"),
    ("/System/Library/Fonts/PingFang.ttc", "auditcjk"),
    ("/System/Library/Fonts/Supplemental/Songti.ttc", "auditcjk"),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "auditcjk"),
    ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", "auditcjk"),
]


def register_cjk_font(page):
    for path, name in CJK_FONTS:
        if os.path.exists(path):
            try:
                page.insert_font(fontname=name, fontfile=path)
                return name
            except Exception:
                continue
    return "china-s"


def load(path, default=None):
    if not path or not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_stem(w):
    year = w.get("year") or "0000"
    wid = re.sub(r"[^A-Za-z0-9]", "", str(w.get("id") or "x"))[:12]
    return f"{year}_{wid}"


def build_md(w, ctx):
    pos_map = {"first": "第一作者", "middle": "中间作者", "last": "末位作者"}
    pos = pos_map.get(w.get("my_position"), str(w.get("my_position") or "—"))
    if w.get("is_corresponding"):
        pos += "（通讯作者）"
    grants = w.get("grants") or []
    ep = ctx.get("epmc_map", {}).get(str(w.get("id"))) or {}
    ep_grants = [f"{g.get('agency') or '未具名'}（{g.get('grant_id')}）" for g in (ep.get("grants") or [])]
    gtxt = "；".join(
        f"{g.get('funder') or '未具名'}" + (f"（{g['award_id']}）" if g.get("award_id") else "")
        for g in grants
    ) or "未标注"
    if ep_grants:
        gtxt += "　｜　Europe PMC： " + "；".join(ep_grants)
    in_main = "—"
    if ctx.get("main_domain") and w.get("domain"):
        in_main = "主线内" if w["domain"] == ctx["main_domain"] else "主线外"
    flags = []
    if str(w.get("id")) in ctx["isolated_ids"]:
        flags.append("**疑似作者档案误并**（与其余成果无合作者交集且学科不重叠）")
    if w.get("is_retracted"):
        flags.append("**已撤稿**")
    if not w.get("doi"):
        flags.append("无 DOI（核查需原文）")
    if not ctx["pdf_map"].get(str(w.get("id"))):
        flags.append("全文未获取（相关维度无法核查）")
    if len(grants) >= 3:
        flags.append(f"单篇标注 {len(grants)} 个基金")

    L = []
    L.append(f"# 审计批注 · {w.get('year')} · {safe_stem(w)}\n")
    L.append(f"**{w.get('title')}**\n")
    L.append("| 字段 | 值 |")
    L.append("|---|---|")
    L.append(f"| 年份 | {w.get('year')} |")
    L.append(f"| 期刊 | {w.get('venue') or '—'} |")
    L.append(f"| 出版商 | {w.get('publisher') or '—'} |")
    L.append(f"| ISSN | {w.get('issn') or '—'} |")
    L.append(f"| DOI | {w.get('doi') or '—'} |")
    L.append(f"| 类型 / 语言 | {w.get('type') or '—'} / {w.get('language') or '—'} |")
    L.append(f"| 开放获取 | {'是' if w.get('is_oa') else '否'}（{w.get('oa_status') or '—'}） |")
    L.append(f"| 作者总数 | {w.get('n_authors')} |")
    L.append(f"| 本人位次 | {pos} |")
    L.append(f"| 被引 | {w.get('cited_by')} |")
    L.append(f"| 基金标注 | {gtxt} |")
    L.append(f"| 主题 | {w.get('domain') or '—'} / {w.get('field') or '—'} / {w.get('topic') or '—'} |")
    if in_main != "—":
        L.append(f"| 主线归属 | {in_main} |")
    L.append(f"| 全文 | {'已获取：' + ctx['pdf_map'][str(w.get('id'))] if ctx['pdf_map'].get(str(w.get('id'))) else ('PMC 开放全文：' + ep['fulltext_file'] if ep.get('fulltext_file') else '未获取')} |")
    if ep.get("pmcid"):
        L.append(f"| PMCID | {ep['pmcid']} |")
    jats = ep.get("jats") or {}
    if jats.get("n_figs") or jats.get("n_tables"):
        L.append(f"| 图表数 | 图 {jats.get('n_figs')} / 表 {jats.get('n_tables')} / 参考文献 {jats.get('n_refs')} |")
    if jats.get("received") or jats.get("accepted"):
        L.append(f"| 收稿→接受 | {jats.get('received') or '—'} → {jats.get('accepted') or '—'} |")
    if flags:
        L.append(f"| 自动标记 | {'；'.join(flags)} |")
    L.append("")

    L.append("## 事实记录（脚本自动填写，可直接引用）\n")
    L.append(f"- 【事实】该文 {w.get('year')} 年发表于《{w.get('venue') or '—'}》，DOI {w.get('doi') or '无'}。")
    pid = _pos_index(w)
    pos_phrase = f"第 {pid} 位" if isinstance(pid, int) else "中间位次"
    L.append(f"- 【事实】本人为 {w.get('n_authors')} 位作者中的{pos_phrase}，"
             f"身份为{pos}。")
    if grants:
        L.append(f"- 【事实】原文标注基金 {len(grants)} 项：{gtxt}。")
    L.append(f"- 【事实】OpenAlex 主题层级：{w.get('domain') or '—'} → {w.get('field') or '—'} → {w.get('subfield') or '—'}。")
    L.append("")

    L.append("## 待核清单\n")
    for c in CHECK_ITEMS:
        L.append(f"- [ ] {c}")
    L.append("")

    L.append("## 审计判断（由审计人填写）\n")
    L.append("| 维度 | 结论 | 依据 |")
    L.append("|---|---|---|")
    for d in ["D2 专业相关性", "D3 期刊质量", "D4 学术规范", "D5 基金合规"]:
        L.append(f"| {d} | | |")
    L.append("")
    L.append("**本篇结论**：（未发现异常 / 需说明的疑点 / 高度可疑 / 证据不足）\n")
    L.append("**需本人说明事项**：\n")
    L.append("**验证路径**：（对方复核时应打开哪个链接、看原文第几页第几图）\n")
    return "\n".join(L)


def _pos_index(w):
    n = w.get("n_authors") or 0
    if n <= 1:
        return 1
    p = w.get("my_position")
    if p == "first":
        return 1
    if p == "last":
        return n
    return "中"


def _pos_cn(w):
    m = {"first": "第一作者", "middle": "中间作者", "last": "末位作者"}
    s = m.get(w.get("my_position"), "—")
    if w.get("is_corresponding"):
        s += "·通讯作者"
    return s


def stamp_pdf(pdf_path, out_path, w, ctx):
    """在 PDF 首页前插入一页审计批注页，另存为工作副本（原文件保持原样）。"""
    try:
        import pymupdf
    except Exception:
        return False
    try:
        doc = pymupdf.open(pdf_path)
        page = doc.new_page(pno=0, width=595, height=842)  # A4
        cjk = register_cjk_font(page)
        title = (w.get("title") or "")[:170]

        def draw(text, y, size, wrap=0):
            fam = cjk if any(ord(c) > 127 for c in text) else "helv"
            if not wrap:
                page.insert_text((56, y), text, fontsize=size, fontname=fam, color=(0.1, 0.1, 0.1))
                return y + size * 1.55 + 3
            lines, cur, width = [], "", 0.0
            for ch in text:
                w = 1.0 if ord(ch) > 127 else 0.52
                if width + w > wrap:
                    lines.append(cur)
                    cur, width = ch, w
                else:
                    cur += ch
                    width += w
            if cur:
                lines.append(cur)
            for ln in lines:
                page.insert_text((56, y), ln, fontsize=size, fontname=fam, color=(0.1, 0.1, 0.1))
                y += size * 1.55
            return y + 3

        y = 72
        y = draw("审计批注", y, 17)
        y = draw("Academic Integrity Audit Annotation", y, 8)
        y += 8
        for text in [
            f"篇目编号：{safe_stem(w)}",
            f"发表年份：{w.get('year')}",
            f"期刊：{(w.get('venue') or '-')[:46]}",
            f"DOI：{w.get('doi') or '-'}",
            f"作者位次：{_pos_cn(w)}（共 {w.get('n_authors')} 位）",
        ]:
            y = draw(text, y, 9.5)
        y += 8
        y = draw("标题", y, 9.5)
        y = draw(title, y, 9.5, wrap=48)
        y += 12
        y = draw("待核项", y, 10.5)
        for c in ["专业相关性", "期刊质量", "作者贡献", "基金标注", "数据与图片", "伦理与注册", "重复发表"]:
            y = draw(f"□  {c}", y, 9.5)
        y += 10
        y = draw("结论：□ 未发现异常    □ 需说明的疑点    □ 高度可疑    □ 证据不足", y, 9.5)
        y += 10
        y = draw("审计人：____________        日期：____________", y, 9.5)
        y += 14
        y = draw("本页由 academic-misconduct-auditor 生成，仅供审计底稿使用；", y, 7)
        y = draw("不构成学术不端认定。原始论文内容未做任何修改。", y, 7)
        page.draw_rect(pymupdf.Rect(46, 40, 549, min(y + 12, 800)), color=(0.55, 0.10, 0.10), width=1.2)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        doc.save(out_path, garbage=1, deflate=True)
        doc.close()
        return True
    except Exception as e:
        print(f"  stamp 失败 {os.path.basename(pdf_path)}: {type(e).__name__}", file=sys.stderr)
        return False


def main():
    ap = argparse.ArgumentParser(description="生成逐篇审计批注")
    ap.add_argument("--works", required=True)
    ap.add_argument("--metrics")
    ap.add_argument("--fulltext", default="fulltext")
    ap.add_argument("--epmc", help="fetch_epmc.py 输出目录（补充付费墙论文的基金信息与 PMC 全文）")
    ap.add_argument("--out", default="annotations")
    ap.add_argument("--stamp", action="store_true", help="在 PDF 首页插入审计批注页")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    payload = load(args.works) or {}
    works = payload.get("works") or []
    metrics = load(args.metrics) or {}
    manifest = load(os.path.join(args.fulltext, "fulltext_manifest.json")) or {}

    pdf_map = {}
    for item in manifest.get("items") or []:
        if item.get("file") and os.path.exists(item["file"]):
            pdf_map[str(item.get("id"))] = item["file"]

    main_domain = ((metrics.get("distributions") or {}).get("by_domain") or {})
    main_domain = next(iter(main_domain), None)
    isolated = set((metrics.get("identity_check") or {}).get("isolated_work_ids") or [])

    ctx = {"main_domain": main_domain, "isolated_ids": isolated, "pdf_map": pdf_map, "epmc_map": {}}

    if args.epmc:
        ep = load(os.path.join(args.epmc, "epmc_records.json")) or {}
        for it in ep.get("items") or []:
            ctx["epmc_map"][str(it.get("id"))] = it

    os.makedirs(args.out, exist_ok=True)
    target = works[: args.limit] if args.limit else works

    rows, stamped = [], 0
    for w in target:
        stem = safe_stem(w)
        md_path = os.path.join(args.out, stem + ".md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(build_md(w, ctx))

        flag = "误并" if str(w.get("id")) in isolated else ""
        if w.get("is_retracted"):
            flag = (flag + " 撤稿").strip()
        rows.append({
            "stem": stem, "year": w.get("year"), "title": w.get("title"),
            "venue": w.get("venue"), "doi": w.get("doi"),
            "position": w.get("my_position"), "flag": flag,
            "pdf": bool(pdf_map.get(str(w.get("id")))), "md": md_path,
        })

        if args.stamp and pdf_map.get(str(w.get("id"))):
            out_pdf = os.path.join(args.out, "pdf", stem + "_annotated.pdf")
            if stamp_pdf(pdf_map[str(w.get("id"))], out_pdf, w, ctx):
                stamped += 1
                print(f"  stamped {stem}")

    L = ["# 审计批注索引\n",
         f"- 批注单 {len(rows)} 份，已插入 PDF 批注页 {stamped} 份",
         f"- 全文已获取 {sum(1 for r in rows if r['pdf'])} 篇，未获取 {sum(1 for r in rows if not r['pdf'])} 篇\n",
         "| 年份 | 篇目 | 期刊 | 位次 | 标记 | 全文 | 批注单 |",
         "|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda x: -(x["year"] or 0)):
        title = (r["title"] or "-").replace("|", "/")[:40]
        L.append(f"| {r['year']} | {title} | {(r['venue'] or '-')[:22]} | {r['position'] or '-'} | "
                 f"{r['flag']} | {'有' if r['pdf'] else '无'} | [{r['stem']}]({os.path.basename(r['md'])}) |")
    L.append("\n## 使用说明\n")
    L.append("- 批注单的「事实记录」部分可直接引用进报告；「审计判断」部分必须结合原文填写，不得凭元数据推断。")
    L.append("- 标记为「误并」的篇目，在核实原文署名单位前应排除出统计口径。")
    L.append("- 全文未获取的篇目，相关维度只能判为「证据不足」，不得判为「未发现异常」。")
    with open(os.path.join(args.out, "index.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    print(f"批注单 {len(rows)} 份 -> {args.out}/")
    print(f"PDF 批注页 {stamped} 份")
    print(f"索引 -> {os.path.join(args.out, 'index.md')}")


if __name__ == "__main__":
    main()
