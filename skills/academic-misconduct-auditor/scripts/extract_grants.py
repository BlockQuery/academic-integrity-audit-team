#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从已下载的全文 PDF 中提取基金资助声明与批准号（D5 核查的前置步骤）

用法:
  python extract_grants.py --works works.json --fulltext fulltext --out grants

为什么需要这个脚本:
  OpenAlex 的 funders 字段只有资助机构名，没有批准号；Crossref 也常缺失。
  基金合规核查（批准号真伪、负责人、依托单位、执行期）必须回到论文原文脚注。
  人工逐篇打开 PDF 抄写既慢又易错，本脚本先做机器初筛，再由审计人核验。

设计原则:
  - 只提取原文出现的文字，不做任何推断或补全
  - 找不到就写"未提取到"，不猜
  - 提取结果一律标记为「待核」，核验动作必须人工到 kd.nsfc.gov.cn 完成

输出:
  grants/grants_extracted.json  机器可读
  grants/grants_extracted.md    待核表（含空白核验列，可打印填写）
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

# 资助段落锚点：英文与中文常见写法
SECTION_RE = re.compile(
    r"(?is)\b(?:funding|financial support|acknowledg(?:e)?ments?|grants?)\b"
    r"|(?:基金|资助|项目支持)"
)
# NSFC 批准号：8 位，常见 8 开头（面上/青年/地区）或 3 开头（部分专项）
NSFC_NO_RE = re.compile(r"(?<![\d.])([38]\d{7})(?![\d.])")
# 带标签的编号（含省级、校级、横向项目）
LABELED_NO_RE = re.compile(
    r"(?:No\.?|Nos\.?|Grant\s*(?:No\.?)?|编号|批准号|项目号)\s*[:：]?\s*([A-Za-z0-9][A-Za-z0-9\-/]{4,24})"
)
FUNDER_HINTS = [
    ("NSFC", r"National Natural Science Foundation of China|国家自然科学基金"),
    ("某省", r"Example Province|某省"),
    ("国家重点研发", r"National Key (?:R&D|Research and Development)"),
    ("省部级", r"Natural Science Foundation of (?:[A-Z][a-z]+\s?){1,3}Province|省自然科学基金"),
    ("校级", r"Fundamental Research Funds|中央高校基本科研业务费"),
    ("其他", r"."),
]


def clean(txt):
    """去掉 URL 与 DOI，避免把其中的数字误认为批准号。"""
    txt = re.sub(r"https?://\S+", " ", txt)
    txt = re.sub(r"\b10\.\d{4,9}/\S+", " ", txt)
    return txt


def extract_sections(text, span=700):
    """截取基金声明附近的文本片段。"""
    out = []
    for m in SECTION_RE.finditer(text):
        s = max(0, m.start() - 60)
        out.append(text[s : m.start() + span])
    # 段落去重：完全相同的前缀只保留一次
    uniq, seen = [], set()
    for seg in out:
        key = seg[:120]
        if key not in seen:
            seen.add(key)
            uniq.append(seg)
    return uniq


def classify_funder(seg):
    for name, pat in FUNDER_HINTS:
        if re.search(pat, seg, re.I):
            return name
    return "未识别"


def main():
    ap = argparse.ArgumentParser(description="提取全文中的基金声明与批准号")
    ap.add_argument("--works", required=True)
    ap.add_argument("--fulltext", default="fulltext")
    ap.add_argument("--out", default="grants")
    args = ap.parse_args()

    try:
        import pymupdf
    except Exception:
        raise SystemExit("需要 pymupdf：python -m pip install pymupdf")

    with open(args.works, "r", encoding="utf-8") as f:
        works = (json.load(f) or {}).get("works") or []
    mf = os.path.join(args.fulltext, "fulltext_manifest.json")
    manifest = json.load(open(mf, encoding="utf-8")) if os.path.exists(mf) else {}
    pdf_by_id = {str(i.get("id")): i.get("file") for i in manifest.get("items") or []}

    os.makedirs(args.out, exist_ok=True)
    rows = []

    for w in works:
        wid = str(w.get("id"))
        rec = {
            "id": wid, "year": w.get("year"), "title": w.get("title"),
            "doi": w.get("doi"), "venue": w.get("venue"),
            "metadata_funders": [g.get("funder") for g in (w.get("grants") or [])],
            "fulltext": pdf_by_id.get(wid), "status": None,
            "segments": [], "nsfc_numbers": [], "labeled_numbers": [],
            "funders_detected": [],
        }
        pdf = pdf_by_id.get(wid)
        if not pdf or not os.path.exists(pdf):
            rec["status"] = "no-fulltext"
            rows.append(rec)
            continue

        try:
            doc = pymupdf.open(pdf)
            text = clean("\n".join(pg.get_text() for pg in doc))
            doc.close()
        except Exception as e:
            rec["status"] = f"read-error:{type(e).__name__}"
            rows.append(rec)
            continue

        segs = extract_sections(text)
        rec["segments"] = [s.strip()[:600] for s in segs[:3]]
        joined = "\n".join(segs)
        rec["nsfc_numbers"] = sorted(set(NSFC_NO_RE.findall(joined)))
        rec["labeled_numbers"] = sorted(set(LABELED_NO_RE.findall(joined)))[:6]
        rec["funders_detected"] = [classify_funder(s) for s in segs[:3]]
        rec["status"] = "extracted" if (rec["nsfc_numbers"] or rec["labeled_numbers"]) else "no-number-found"
        rows.append(rec)

    payload = {
        "generated_at": __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
        "policy": "批准号仅来自论文原文文字，未经推断。所有号码必须到 kd.nsfc.gov.cn 人工核验后方可写入结论。",
        "stats": {
            "total": len(rows),
            "with_fulltext": sum(1 for r in rows if r["fulltext"]),
            "with_number": sum(1 for r in rows if r["nsfc_numbers"] or r["labeled_numbers"]),
            "no_fulltext": sum(1 for r in rows if r["status"] == "no-fulltext"),
        },
        "items": rows,
    }
    jout = os.path.join(args.out, "grants_extracted.json")
    with open(jout, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    L = [f"# 基金标注提取与核验表\n",
         f"- 生成时间：{payload['generated_at']}",
         f"- 有全文 {payload['stats']['with_fulltext']} 篇，其中提取到编号 {payload['stats']['with_number']} 篇",
         f"- 口径：{payload['policy']}\n",
         "## 待核表（核验列由审计人填写）\n",
         "| 年份 | 论文 | 提取到的批准号 | 资助机构 | 项目负责人 | 依托单位 | 起止年月 | 结论 |",
         "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if not r["fulltext"]:
            continue
        title = (r["title"] or "-").replace("|", "/")[:34]
        nums = "；".join(r["nsfc_numbers"] + r["labeled_numbers"][:3]) or "未提取到"
        funders = "、".join(sorted(set(r["funders_detected"]))) or "—"
        L.append(f"| {r['year']} | {title} | {nums} | {funders} |  |  |  |  |")
    L.append("\n## 原文依据（可直接引用为附件）\n")
    for r in rows:
        if not r["segments"]:
            continue
        L.append(f"### {r['year']} {r['title']}\n")
        L.append(f"DOI：{r['doi']}　全文：`{r['fulltext']}`\n")
        for s in r["segments"][:1]:
            L.append("> " + s.replace("\n", " ")[:520] + "\n")
    L.append("\n## 未获取全文（无法核验基金标注）\n")
    for r in rows:
        if r["status"] == "no-fulltext":
            L.append(f"- {r['year']} {r['title']}｜DOI {r['doi']}｜元数据标有：{'、'.join([x for x in r['metadata_funders'] if x]) or '无'}")
    L.append("\n> 上述篇目在拿到全文前，D5 维度只能记为「证据不足」，不得记为「未发现异常」。")

    mout = os.path.join(args.out, "grants_extracted.md")
    with open(mout, "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    print(f"有全文 {payload['stats']['with_fulltext']}/{payload['stats']['total']} 篇，"
          f"提取到编号 {payload['stats']['with_number']} 篇")
    for r in rows:
        if r["nsfc_numbers"]:
            print(f"  {r['year']} {r['title'][:44]} -> {', '.join(r['nsfc_numbers'])}")
    print(f"待核表 -> {mout}")


if __name__ == "__main__":
    main()
