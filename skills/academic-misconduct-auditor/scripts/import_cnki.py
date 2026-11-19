#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导入中文数据库导出的题录，合并进 works.json

用法:
  python import_cnki.py --input 知网导出.txt --works works.json --name "张三" --out works_merged.json
  python import_cnki.py --input refs.ris --works works.json --name "张三" --default-field 示例学科

为什么用"导出-导入"而不是直接抓:
  知网、万方、维普均有强反爬（实测：CNKI SSL 证书拦截 / 百度学术 403 / 维普 412），
  且抓取需登录态与验证码。直接爬既不稳定也可能违反服务条款。
  导出题录是各家都提供的标准功能（一次可导几十到几百条），
  格式规范、字段完整、可重复，是更可靠的工程路径。

支持格式（自动识别）:
  - CNKI 文本导出（SrcDatabase-来源库 / Title-题名 开头）
  - NoteExpress / CNKI Refworks
  - RIS（EndNote、Zotero、NoteExpress 通用）
  - EndNote ENW（%0 / %A 开头）

核心功能:
  1. 解析题录
  2. 按姓名自动判定本人作者位次（这次务必判对——位次错会直接扭曲"是否主导"的结论）
  3. 与已有 works.json 去重合并（标题归一化 + 年份）
  4. 按期刊名推断学科域，使中文成果也能进入专业跨度分析
  5. 输出导入报告：新增/重复/未匹配到本人 三类明细
"""

import argparse
import hashlib
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 中文期刊名 -> OpenAlex 学科域/领域（用于让中文成果进入分布统计）
FIELD_HINTS = [
    (r"示例学科|牙|颌面|齿", "Health Sciences", "Dentistry"),
    (r"放射|影像|医学影像|超声|核医学", "Health Sciences", "Radiology"),
    (r"护理", "Health Sciences", "Nursing"),
    (r"中医|中药|针灸|中西医", "Health Sciences", "Complementary and Alternative Medicine"),
    (r"药理|药学|药物", "Health Sciences", "Pharmacology"),
    (r"公共卫生|预防|流行病|卫生管理", "Health Sciences", "Public Health"),
    (r"肿瘤|癌症", "Health Sciences", "Oncology"),
    (r"内科|外科|临床|医学|医院|诊疗|治疗", "Health Sciences", "Medicine"),
    (r"生物|基因|蛋白|细胞|分子", "Life Sciences", "Biochemistry, Genetics and Molecular Biology"),
    (r"神经|脑", "Life Sciences", "Neuroscience"),
    (r"材料|合金|陶瓷|高分子", "Physical Sciences", "Materials Science"),
    (r"化学", "Physical Sciences", "Chemistry"),
    (r"计算机|软件|算法|人工智能|信息", "Physical Sciences", "Computer Science"),
    (r"工程|机械|电子|建筑", "Physical Sciences", "Engineering"),
    (r"数学|统计", "Physical Sciences", "Mathematics"),
    (r"经济|管理|会计|金融", "Social Sciences", "Economics, Econometrics and Finance"),
    (r"教育|教学", "Social Sciences", "Education"),
]

CNKI_MAP = {
    "Title-题名": "title", "Author-作者": "authors", "Source-文献来源": "venue",
    "Year-年": "year", "PubTime-发表时间": "pubtime", "Volume-卷": "volume",
    "Period-期": "issue", "PageCount-页码": "pages", "Fund-基金": "fund",
    "ISSN-国际标准刊号": "issn", "Summary-摘要": "abstract", "Organ-单位": "org",
    "Keyword-关键词": "keywords", "FirstDuty-第一责任人": "first_duty",
}


def norm_title(t):
    if not t:
        return ""
    t = re.sub(r"[\s\u3000]+", "", t)
    t = re.sub(r"[，,。.、；;：:！!？?（）()\[\]【】\"'“”‘’\-—_]", "", t)
    return t.lower()


def infer_field(venue):
    if not venue:
        return None, None
    for pat, domain, field in FIELD_HINTS:
        if re.search(pat, venue):
            return domain, field
    return None, None


def split_authors(s):
    if not s:
        return []
    s = s.replace("；", ";").replace("，", ",")
    parts = re.split(r"[;,]", s)
    out = []
    for p in parts:
        p = p.strip()
        p = re.sub(r"\d+$", "", p).strip()  # 去掉上标数字
        if p:
            out.append(p)
    return out


def find_position(authors, names):
    """names 可以是字符串或列表。返回 (位次, 匹配方式, 命中的名字)。"""
    if isinstance(names, str):
        names = [names]
    names = [n.strip() for n in names if n and n.strip()]
    if not authors or not names:
        return None, None, None
    for i, a in enumerate(authors, 1):
        for n in names:
            if a.strip() == n:
                return i, "精确", n
    for i, a in enumerate(authors, 1):
        for n in names:
            if n in a or a in n:
                return i, "包含", n
    return None, None, None


def parse_cnki(text):
    """CNKI 的 '字段-中文: 值' 文本格式。"""
    recs, cur = [], {}
    for line in text.splitlines():
        if not line.strip():
            if cur:
                recs.append(cur)
                cur = {}
            continue
        m = re.match(r"^\s*([A-Za-z]+-[^\s:：]{1,20})\s*[:：]\s*(.*)$", line)
        if m:
            k, v = m.group(1), m.group(2).strip()
            cur[k] = (cur.get(k, "") + " " + v).strip() if k in cur else v
        elif cur and "title" in {CNKI_MAP.get(k) for k in cur}:
            # 续行（摘要常换行）
            last = list(cur)[-1]
            cur[last] = (cur[last] + " " + line.strip()).strip()
    if cur:
        recs.append(cur)
    out = []
    for r in recs:
        item = {}
        for k, v in r.items():
            key = CNKI_MAP.get(k)
            if key:
                item[key] = v
        if item.get("title"):
            out.append(item)
    return out


def parse_ris(text):
    """RIS: TY/AU/TI/JO/PY/DO/AB/ER，每条以 ER 结束。"""
    recs, cur = [], {}
    for line in text.splitlines():
        m = re.match(r"^([A-Z][A-Z0-9])\s{2}-\s?(.*)$", line)
        if not m:
            continue
        tag, val = m.group(1), m.group(2).strip()
        if tag == "ER":
            if cur.get("TI"):
                recs.append(cur)
            cur = {}
            continue
        cur.setdefault(tag, []).append(val)
    if cur.get("TI"):
        recs.append(cur)
    out = []
    for r in recs:
        out.append({
            "title": (r.get("TI") or [""])[0],
            "authors": ";".join(r.get("AU") or []),
            "venue": (r.get("JO") or r.get("T2") or r.get("JA") or [""])[0],
            "year": (r.get("PY") or r.get("Y1") or [""])[0],
            "doi": (r.get("DO") or [""])[0],
            "abstract": (r.get("AB") or [""])[0],
            "issn": (r.get("SN") or [""])[0],
            "fund": "",
        })
    return [x for x in out if x["title"]]


def parse_enw(text):
    """EndNote ENW: %0 类型 / %A 作者 / %T 标题 / %J 期刊 / %D 年 / %R DOI"""
    recs, cur = [], {}
    for line in text.splitlines():
        if line.startswith("%0"):
            if cur.get("T"):
                recs.append(cur)
            cur = {}
            continue
        m = re.match(r"^(%[A-Z@!#$&()*+^`~])\s(.*)$", line)
        if not m:
            continue
        tag, val = m.group(1), m.group(2).strip()
        if tag == "%A":
            cur.setdefault("A", []).append(val)
        else:
            cur[tag] = val
    if cur.get("T"):
        recs.append(cur)
    out = []
    for r in recs:
        out.append({
            "title": r.get("T", ""),
            "authors": ";".join(r.get("A") or []),
            "venue": r.get("J", ""),
            "year": r.get("D", ""),
            "doi": r.get("R", ""),
            "abstract": r.get("X", ""),
            "issn": r.get("@", ""),
            "fund": "",
        })
    return [x for x in out if x["title"]]


def parse_csv(text):
    """CSV：title,authors,venue,year,volume,issue,pages,doi,fund,keywords
    字段名大小写不敏感，缺列自动跳过。适合把搜索引擎/人工检索结果整理后导入。
    """
    import csv as _csv
    import io as _io
    rdr = _csv.DictReader(_io.StringIO(text))
    if not rdr.fieldnames:
        return []
    alias = {
        "title": "title", "题名": "title", "篇名": "title", "标题": "title",
        "authors": "authors", "作者": "authors",
        "venue": "venue", "期刊": "venue", "刊名": "venue", "来源": "venue",
        "year": "year", "年份": "year", "年": "year",
        "volume": "volume", "卷": "volume",
        "issue": "issue", "期": "issue",
        "pages": "pages", "页码": "pages",
        "doi": "doi",
        "fund": "fund", "基金": "fund", "基金项目": "fund",
        "keywords": "keywords", "关键词": "keywords",
        "abstract": "abstract", "摘要": "abstract",
        "org": "org", "单位": "org", "作者单位": "org",
    }
    out = []
    for row in rdr:
        item = {}
        for k, v in row.items():
            if k is None or v is None:
                continue
            kk = k.lstrip("\ufeff").strip()
            key = alias.get(kk.lower()) or alias.get(kk)
            if key and str(v).strip():
                item[key] = str(v).strip()
        if item.get("title"):
            out.append(item)
    return out


def detect_format(text):
    if re.search(r"^\s*(SrcDatabase-|Title-题名)", text, re.M):
        return "cnki", parse_cnki
    if re.search(r"^TY\s{2}-", text, re.M):
        return "ris", parse_ris
    if re.search(r"^%0\s", text, re.M):
        return "enw", parse_enw
    head = text.split("\n", 1)[0].lower()
    if "," in head and re.search(r"title|题名|篇名|作者|authors", head):
        return "csv", parse_csv
    return None, None


def extract_year(s):
    m = re.search(r"(19|20)\d{2}", str(s or ""))
    return int(m.group(0)) if m else None


def to_work(item, names, idx, default_field=None):
    authors = split_authors(item.get("authors"))
    pos, how, hit_name = find_position(authors, names)
    year = extract_year(item.get("year") or item.get("pubtime"))
    venue = (item.get("venue") or "").strip()
    domain, field = infer_field(venue)
    if not field and default_field:
        domain, field = infer_field(default_field)

    others = [a for a in authors if a.strip() != hit_name][:15]
    fund = (item.get("fund") or "").strip()
    grants = []
    if fund:
        for m in re.finditer(r"([\u4e00-\u9fa5A-Za-z（）()·\s]{2,40}?)\s*[（(]?\s*(?:No\.?|编号|批准号)?\s*([38]\d{7}|[A-Z]{2,}\d{4,})", fund):
            grants.append({"funder": m.group(1).strip(" ，,、"), "award_id": m.group(2)})
        if not grants:
            grants.append({"funder": fund[:80], "award_id": None})

    if pos is None:
        position = None
    elif pos == 1:
        position = "first"
    elif pos == len(authors):
        position = "last"
    else:
        position = "middle"

    wid = "cnki_" + hashlib.md5(
        (norm_title(item.get("title")) + str(year or "")).encode("utf-8")
    ).hexdigest()[:12]

    return {
        "id": wid,
        "doi": (item.get("doi") or "").strip() or None,
        "title": item.get("title", "").strip(),
        "year": year,
        "date": item.get("pubtime") or (f"{year}-01-01" if year else None),
        "type": "article",
        "venue": venue or None,
        "publisher": None,
        "issn": item.get("issn") or None,
        "is_oa": False,
        "oa_status": None,
        "oa_url": None,
        "pdf_url": None,
        "license": None,
        "landing_page": None,
        "cited_by": None,
        "is_retracted": None,
        "language": "zh",
        "n_authors": len(authors),
        "my_position": position,
        "is_corresponding": bool(item.get("first_duty") and hit_name and hit_name in item.get("first_duty", "")),
        "my_institutions": [item.get("org")] if item.get("org") else [],
        "coauthors": others,
        "grants": grants,
        "field": field,
        "domain": domain,
        "subfield": field,
        "topic": item.get("keywords") or None,
        "topic_score": None,
        "referenced_works_count": None,
        "source": "cnki-import",
        "author_position_raw": {
            "position": pos, "match": how, "matched_name": hit_name,
            "total": len(authors), "authors": authors,
        },
        "volume": item.get("volume"), "issue": item.get("issue"), "pages": item.get("pages"),
        "abstract": (item.get("abstract") or "")[:1500] or None,
    }


def main():
    ap = argparse.ArgumentParser(description="导入中文题录并合并进 works.json")
    ap.add_argument("--input", required=True, help="导出的题录文件（txt/ris/enw）")
    ap.add_argument("--works", required=True, help="已有 works.json（OpenAlex 采集结果）")
    ap.add_argument("--name", required=True, help="本人姓名，用于判定作者位次")
    ap.add_argument("--alias", help="其他姓名写法，逗号分隔。中文题录用中文名，英文题录用拼音，如 张三,San Zhang")
    ap.add_argument("--out", help="合并后的输出路径，默认覆盖 works.json 旁的 *_merged.json")
    ap.add_argument("--default-field", help="题录无期刊可判时用此领域兜底，如 示例学科")
    ap.add_argument("--report", help="导入报告路径")
    args = ap.parse_args()

    names = [args.name] + [x.strip() for x in (args.alias or "").replace("，", ",").split(",") if x.strip()]
    names = list(dict.fromkeys(names))

    with open(args.input, "r", encoding="utf-8-sig", errors="ignore") as f:
        text = f.read()
    fmt, parser = detect_format(text)
    if not parser:
        raise SystemExit("无法识别格式。支持：CNKI 文本导出 / RIS / EndNote ENW。")
    items = parser(text)
    print(f"识别格式：{fmt}，解析出 {len(items)} 条题录")

    with open(args.works, "r", encoding="utf-8") as f:
        payload = json.load(f)
    works = payload.get("works") or []

    existing = {}
    for w in works:
        existing[norm_title(w.get("title"))] = w
        if w.get("doi"):
            existing[w["doi"].lower()] = w

    added, dup, unmatched, no_year = [], [], [], []
    for i, it in enumerate(items, 1):
        w = to_work(it, names, i, args.default_field)
        key = norm_title(w["title"])
        if key in existing or (w.get("doi") and w["doi"].lower() in existing):
            dup.append(w)
            continue
        if w["author_position_raw"]["position"] is None:
            unmatched.append(w)
            continue
        if not w["year"]:
            no_year.append(w)
        added.append(w)
        existing[key] = w

    merged = sorted(works + added, key=lambda x: (x.get("year") or 0))
    out_path = args.out or os.path.join(os.path.dirname(args.works) or ".", "works_merged.json")
    payload["works"] = merged
    payload["cnki_import"] = {
        "input": args.input, "format": fmt, "parsed": len(items),
        "added": len(added), "duplicate": len(dup), "name_unmatched": len(unmatched),
        "no_year": len(no_year), "name_used": names,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    L = [
        f"# 中文题录导入报告\n",
        f"- 来源文件：`{args.input}`（格式 {fmt}）",
        f"- 解析 {len(items)} 条｜新增 **{len(added)}**｜重复 {len(dup)}｜"
        f"未匹配到本人 {len(unmatched)}｜无年份 {len(no_year)}",
        f"- 姓名判据：{'、'.join(names)}",
        f"- 合并后总篇数：{len(merged)}\n",
        "## 新增篇目（按年份）\n",
        "| 年份 | 标题 | 期刊 | 位次 | 作者总数 | 匹配 | 基金 |",
        "|---|---|---|---|---|---|---|",
    ]
    for w in sorted(added, key=lambda x: -(x.get("year") or 0)):
        raw = w["author_position_raw"]
        pos = raw.get("position")
        pos_txt = f"{pos}/{raw.get('total')}" if pos else "—"
        fund = w["grants"][0]["award_id"] if w.get("grants") and w["grants"][0].get("award_id") else ""
        L.append(f"| {w.get('year') or '—'} | {(w['title'] or '')[:44]} | {(w.get('venue') or '—')[:20]} | "
                 f"{pos_txt} | {raw.get('total')} | {raw.get('match') or '—'} | {fund} |")

    if unmatched:
        L += ["\n## 未匹配到本人的题录（需人工确认是否同一人）\n",
              "以下题录的作者列表中未找到「" + args.name + "」，两种情况：姓名写法不同，或该文非本人。**未确认前不得计入成果。**\n"]
        for w in unmatched:
            L.append(f"- {w.get('year') or '—'} {w['title']}｜作者：{'、'.join(w['author_position_raw']['authors'][:6])}")

    if dup:
        L.append(f"\n## 重复（已存在，未重复计入）\n")
        L.append(f"共 {len(dup)} 条，多为同一论文的中英文双版或已由 OpenAlex 收录。")

    L += ["\n## 注意事项\n",
          "- 中文题录**无 DOI、无摘要时**，图片复用与数据一致性核查须取原文 PDF。",
          "- 位次判定依赖作者姓名精确匹配。若同名作者混入，会污染统计——务必核对「未匹配」清单。",
          "- `field/domain` 由期刊名关键词推断，仅为分布统计服务，不作为专业符合性的唯一依据。",
          "- 知网导出的「Fund-基金」字段需核对：部分记录只写基金名不写批准号。"]

    rp = args.report or os.path.join(os.path.dirname(out_path) or ".", "cnki_import_report.md")
    with open(rp, "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    print(f"新增 {len(added)}｜重复 {len(dup)}｜未匹配 {len(unmatched)}｜合并后 {len(merged)} 篇")
    print(f"合并结果 -> {out_path}\n导入报告 -> {rp}")
    if unmatched:
        print(f"⚠ 有 {len(unmatched)} 条未在作者列表中找到「{'/'.join(names)}」，请核对报告后再决定是否采信。")


if __name__ == "__main__":
    main()
