#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""学者身份消歧与论文元数据采集（OpenAlex 主源 / Crossref 兜底）

用法:
  # 1) 候选检索（消歧阶段，只读，不产生指控）
  python fetch_scholar.py candidates --name "张三" --org "示例大学" --field "示例学科" --out cand.json

  # 2) 按确认后的 OpenAlex ID 拉全量论文
  python fetch_scholar.py works --author-id A0000000000 --out works.json

  # 3) 一站式（跳过人工确认，仅用于复核，正式审计禁止跳过确认）
  python fetch_scholar.py works --name "张三" --org "示例大学" --auto --out works.json

设计约束:
  - 只读取公开元数据，不抓取全文、不下载 PDF、不接触个人隐私字段
  - 所有输出带 retrieved_at 时间戳，供报告复现
  - 遵守 polite pool（mailto）与退避重试，避免触发 429
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = "https://api.openalex.org"
UA = "academic-misconduct-auditor/1.0 (mailto:{mailto})"

# 中文领域词 -> OpenAlex 学科词（仅用于候选排序，不用于定性）
FIELD_MAP = {
    "示例学科": ["Dentistry", "Oral", "Periodont"],
    "牙": ["Dentistry", "Odont"],
    "临床": ["Medicine", "Clinical"],
    "内科": ["Medicine", "Internal"],
    "外科": ["Surgery", "Medicine"],
    "影像": ["Radiology", "Imaging"],
    "放射": ["Radiology"],
    "检验": ["Immunology", "Microbiology", "Laboratory"],
    "药理": ["Pharmacology", "Pharmacy"],
    "药学": ["Pharmacology", "Pharmacy", "Drug"],
    "公共卫生": ["Public Health", "Epidemiology"],
    "预防": ["Public Health", "Preventive"],
    "护理": ["Nursing"],
    "中医": ["Traditional Chinese", "Complementary and Alternative"],
    "中药": ["Traditional Chinese", "Phytotherapy"],
    "生物": ["Biology", "Biochemistry", "Genetics"],
    "材料": ["Materials Science", "Biomaterials"],
    "化学": ["Chemistry"],
    "物理": ["Physics"],
    "计算机": ["Computer Science"],
    "人工智能": ["Artificial Intelligence", "Computer Science"],
    "工程": ["Engineering"],
    "数学": ["Mathematics"],
    "统计": ["Statistics"],
    "环境": ["Environmental Science"],
    "农": ["Agricultural"],
    "食品": ["Food Science"],
    "经济": ["Economics"],
    "管理": ["Business", "Management"],
    "心理": ["Psychology"],
    "教育": ["Education"],
    "法律": ["Law"],
}
WORK_SELECT = ",".join([
    "id", "doi", "title", "display_name", "publication_year", "publication_date",
    "type", "primary_location", "best_oa_location", "open_access", "authorships", "funders",
    "topics", "primary_topic", "cited_by_count", "is_retracted", "language",
    "referenced_works_count", "locations_count",
])


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def api_get(path, params, mailto, retries=5, verbose=True):
    q = dict(params)
    q["mailto"] = mailto
    url = f"{BASE}{path}?{urllib.parse.urlencode(q)}"
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": UA.format(mailto=mailto), "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code in (429, 500, 502, 503, 504):
                wait = min(2 ** attempt * 2, 30)
                if verbose:
                    print(f"  [retry {attempt+1}/{retries}] {last} -> sleep {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            raise SystemExit(f"API 拒绝请求: {last} @ {url}")
        except Exception as e:  # 网络抖动
            last = f"{type(e).__name__}: {e}"
            wait = min(2 ** attempt * 2, 30)
            if verbose:
                print(f"  [retry {attempt+1}/{retries}] {last} -> sleep {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise SystemExit(f"API 连续失败: {last} @ {url}")


def norm_key(s):
    return (s or "").replace(" ", "").replace("　", "").lower()


def inst_names(author):
    names = []
    for inst in author.get("last_known_institutions") or []:
        if inst.get("display_name"):
            names.append(inst["display_name"])
    for aff in author.get("affiliations") or []:
        nm = (aff.get("institution") or {}).get("display_name")
        if nm:
            names.append(nm)
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def author_topics(author, limit=6):
    out = []
    for t in (author.get("topics") or [])[:limit]:
        out.append({
            "topic": t.get("display_name"),
            "field": ((t.get("field") or {}).get("display_name")),
            "domain": ((t.get("domain") or {}).get("display_name")),
            "count": t.get("count"),
        })
    return out


def resolve_institutions(org, mailto, limit=5):
    """把中文/俗称机构名解析为 OpenAlex 机构记录（含标准英文名与别名）。"""
    if not org:
        return []
    try:
        data = api_get("/institutions", {"search": org, "per_page": limit}, mailto, retries=3, verbose=False)
    except SystemExit:
        return []
    out = []
    for i in data.get("results", []):
        names = [i.get("display_name")] + (i.get("display_name_alternatives") or [])
        out.append({
            "id": (i.get("id") or "").rsplit("/", 1)[-1],
            "name": i.get("display_name"),
            "names": [n for n in names if n][:8],
            "country": i.get("country_code"),
            "type": i.get("type"),
            "works_count": i.get("works_count"),
        })
    return out


def field_terms(field):
    """把领域词展开为中英文匹配词表。"""
    if not field:
        return []
    terms = [field]
    for k, v in FIELD_MAP.items():
        if k in field or field in k:
            terms.extend(v)
    return list(dict.fromkeys(terms))


def score_candidate(author, org, field, inst_records=None, field_expanded=None):
    """机构 + 领域匹配打分。分数只用于排序候选，不构成任何实质判断。

    返回 (score, why, flags)。flags 是给人看的风险提示，用来抵消"分数最高就是本人"
    这个最危险的直觉——OpenAlex 的 author 档案会把多个同名者并进一条记录，
    也会把同一个人的成果拆成几条碎片档案。前者会让分数虚高，后者会让分数虚低。
    """
    score, why, flags = 0, [], []
    insts = inst_names(author)
    blob = norm_key(" ".join(insts))
    matched_names = []
    if org:
        hit = False
        for rec in (inst_records or []):
            for nm in rec["names"]:
                if norm_key(nm) and norm_key(nm) in blob:
                    score += 70 if rec["name"] == nm else 60
                    why.append(f"机构命中:{nm}")
                    matched_names.append(nm)
                    hit = True
                    break
            if hit:
                break
        if not hit:
            org_key = norm_key(org)
            if org_key and org_key in blob:
                score += 60
                why.append(f"机构原文命中:{org}")
                matched_names.append(org)
            else:
                for rec in (inst_records or []):
                    for token in [t for t in rec["name"].split() if len(t) > 2]:
                        if norm_key(token) in blob:
                            score += 25
                            why.append(f"机构词命中:{token}")
                            hit = True
                            break
                    if hit:
                        break
    if field:
        tnames = " ".join(
            norm_key((t.get("topic") or "") + (t.get("field") or "") + (t.get("domain") or ""))
            for t in author_topics(author, 15)
        )
        hit_terms = [t for t in (field_expanded or [field]) if norm_key(t) and norm_key(t) in tnames]
        if hit_terms:
            score += 45
            why.append(f"领域命中:{'/'.join(hit_terms[:2])}")
        else:
            score -= 15
            why.append("领域未命中")
    wc = author.get("works_count") or 0
    if wc:
        score += min(20, round(wc ** 0.5))
        why.append(f"论文量:{wc}")
    if author.get("orcid"):
        score += 8
        why.append("有 ORCID")

    # —— 并档 / 碎片识别：分数的两个主要失真来源 ——
    if matched_names and insts:
        foreign = [i for i in insts
                   if not any(norm_key(nm) in norm_key(i) for nm in matched_names)]
        if foreign:
            score -= min(30, 12 * len(foreign))
            why.append(f"非目标机构{len(foreign)}个:-{min(30, 12 * len(foreign))}")
            if len(foreign) >= 2:
                flags.append(
                    f"merged_suspect: 档案含 {len(foreign)} 个非目标机构（{'；'.join(foreign[:3])}），"
                    f"极可能是多个同名者被并成一条记录。禁止按本 ID 全量取数，必须逐篇核单位与通讯邮箱"
                )
            else:
                flags.append(
                    f"co_affiliation_or_merge: 含 1 个非目标机构（{foreign[0]}），"
                    f"可能是兼职/就读/合作，也可能是并档，需逐篇核"
                )
        elif wc <= 3:
            flags.append(
                f"fragment_suspect: 机构一致但仅 {wc} 篇，可能是同一自然人的碎片档案，"
                f"需按通讯邮箱或长期合作者与主档归并后去重"
            )
    return score, why, flags



def name_variants(name):
    """生成常见的中英文姓名写法变体（西文姓名顺序不固定）。"""
    if not name:
        return []
    parts = name.replace("-", " ").split()
    out = [name]
    if len(parts) == 2:
        a, b = parts
        out += [f"{b} {a}", f"{a}-{b}", f"{b}-{a}"]
    return list(dict.fromkeys(out))


def stage_candidates(args):
    inst_records = resolve_institutions(args.org, args.mailto) if args.org else []
    warn = None
    if args.org and not inst_records:
        warn = (f"机构「{args.org}」在 OpenAlex 无记录。可能是更名前的旧称、英文名差异，"
                f"或该机构尚未被收录。本次未按机构过滤，下列候选可能与该单位无关——"
                f"请改用该机构的英文标准名（如 示例大学 → Example University）重试。")
        print("⚠ " + warn, file=sys.stderr)
    elif inst_records:
        print(f"机构解析: {args.org} -> " + "；".join(
            f"{r['name']}({r['id']},{r['country']})" for r in inst_records[:3]))
        print("  提示: 若首选机构不符，请改用英文全名或直接用 --author-id 指定。", file=sys.stderr)

    def build_params(nm):
        p = {"per_page": args.per_page, "sort": "works_count:desc"}
        f = []
        if nm:
            f.append(f"display_name.search:{nm}")
        if args.orcid_id:
            f.append(f"orcid:{args.orcid_id}")
        if inst_records:
            f.append(f"affiliations.institution.id:{inst_records[0]['id']}")
        if f:
            p["filter"] = ",".join(f)
        elif nm:
            p["search"] = nm
        return p

    if not args.name and not args.orcid_id:
        raise SystemExit("需要 --name 或 --orcid-id")

    data = api_get("/authors", build_params(args.name), args.mailto)
    tried, used_name = [args.name], args.name
    if not (data.get("results") or []) and args.name:
        for v in name_variants(args.name)[1:]:
            tried.append(v)
            data = api_get("/authors", build_params(v), args.mailto)
            if data.get("results"):
                used_name = v
                print(f"  [姓名变体命中] {args.name} → {v}", file=sys.stderr)
                break
    expanded = field_terms(args.field)
    rows = []
    for a in data.get("results", []):
        score, why, flags = score_candidate(a, args.org, args.field, inst_records, expanded)
        rows.append({
            "openalex_id": (a.get("id") or "").rsplit("/", 1)[-1],
            "name": a.get("display_name"),
            "name_variants": (a.get("display_name_alternatives") or [])[:8],
            "institutions": inst_names(a),
            "works_count": a.get("works_count"),
            "cited_by_count": a.get("cited_by_count"),
            "h_index": (a.get("summary_stats") or {}).get("h_index"),
            "orcid": a.get("orcid"),
            "topics": author_topics(a),
            "match_score": score,
            "match_reason": why,
            "risk_flags": flags,
        })
    rows.sort(key=lambda r: (-r["match_score"], -(r["works_count"] or 0)))
    payload = {
        "stage": "candidates",
        "query": {"name": args.name, "org": args.org, "field": args.field, "orcid": args.orcid_id},
        "resolved_institutions": inst_records,
        "field_terms": expanded,
        "name_variants_tried": tried,
        "name_variant_used": used_name,
        "warning": warn,
        "source": "OpenAlex /authors",
        "retrieved_at": now_iso(),
        "total_returned": len(rows),
        "note": ("match_score 仅为排序线索，不代表身份确认。必须由用户确认后再采集论文。"
                 "另注意：OpenAlex 会把同名者并成一条档案（分数虚高），也会把同一人的成果拆成碎片档案（分数虚低），"
                 "选人前务必逐个看 risk_flags。"),
        "candidates": rows,
    }
    out = args.out or f"candidates_{args.name or args.orcid_id}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"候选 {len(rows)} 位 -> {out}")
    for i, r in enumerate(rows[:10], 1):
        inst = "; ".join(r["institutions"][:2]) or "-"
        print(f"  [{i}] {r['name']} | {inst} | works={r['works_count']} | h={r['h_index']} | score={r['match_score']} -> {r['openalex_id']}")
        for fl in (r.get("risk_flags") or []):
            tag = fl.split(":", 1)[0]
            msg = fl.split(":", 1)[1].strip() if ":" in fl else fl
            print(f"      ⚠ {tag} — {msg}")
    if any(r.get("risk_flags") for r in rows):
        print("\n⚠ 有候选带风险标记：并档会让分数虚高、碎片档案会让分数虚低。"
              "\n  不要按分数直接选人，先按 risk_flags 逐条排除/归并。")

    if rows:
        print("\n下一步: 用户确认后执行  python fetch_scholar.py works --author-id <ID>")
    else:
        print("\n未命中。中文姓名需转拼音/英文署名后重试（如 张三 -> San Zhang）。")
    return rows


def pick_author(args):
    if args.author_id:
        a = api_get(f"/authors/{args.author_id}", {}, args.mailto)
        return a
    rows = stage_candidates(args)
    if not rows:
        raise SystemExit("未检索到候选作者，请换用拼音/英文名或补充机构。")
    if not args.auto:
        raise SystemExit("需要 --author-id 或 --auto。正式审计必须先由用户确认候选身份。")
    top = rows[0]
    print(f"[auto] 采用首选候选: {top['name']} ({top['openalex_id']})")
    return api_get(f"/authors/{top['openalex_id']}", {}, args.mailto)


def norm_work(w, target_author_id):
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}
    best = w.get("best_oa_location") or {}
    pt = w.get("primary_topic") or {}
    auths = w.get("authorships") or []
    mine, others = None, []
    for a in auths:
        aid = ((a.get("author") or {}).get("id") or "").rsplit("/", 1)[-1]
        nm = (a.get("author") or {}).get("display_name")
        if aid == target_author_id:
            mine = a
        elif nm:
            others.append(nm)
    grants = []
    for g in (w.get("grants") or []):
        grants.append({
            "funder": g.get("funder_display_name"),
            "award_id": g.get("award_id"),
        })
    for f in (w.get("funders") or []):
        name = f.get("display_name")
        if name and not any(name == g["funder"] for g in grants):
            grants.append({
                "funder": name,
                "award_id": None,
                "funder_id": (f.get("id") or "").rsplit("/", 1)[-1],
                "ror": f.get("ror"),
            })
    return {
        "id": (w.get("id") or "").rsplit("/", 1)[-1],
        "doi": (w.get("doi") or "").replace("https://doi.org/", "") or None,
        "title": w.get("display_name") or w.get("title"),
        "year": w.get("publication_year"),
        "date": w.get("publication_date"),
        "type": w.get("type"),
        "venue": src.get("display_name"),
        "publisher": src.get("host_organization_name"),
        "issn": src.get("issn_l"),
        "is_oa": (w.get("open_access") or {}).get("is_oa"),
        "oa_status": (w.get("open_access") or {}).get("oa_status"),
        "oa_url": (w.get("open_access") or {}).get("oa_url"),
        "pdf_url": best.get("pdf_url"),
        "license": best.get("license"),
        "landing_page": best.get("landing_page_url") or loc.get("landing_page_url"),
        "cited_by": w.get("cited_by_count"),
        "is_retracted": w.get("is_retracted"),
        "language": w.get("language"),
        "n_authors": len(auths),
        "my_position": (mine or {}).get("author_position"),
        "is_corresponding": (mine or {}).get("is_corresponding"),
        "my_institutions": [
            i.get("display_name") for i in ((mine or {}).get("institutions") or []) if i.get("display_name")
        ],
        "coauthors": others[:15],
        "grants": grants,
        "field": ((pt.get("field") or {}).get("display_name")),
        "domain": ((pt.get("domain") or {}).get("display_name")),
        "subfield": ((pt.get("subfield") or {}).get("display_name")),
        "topic": pt.get("display_name"),
        "topic_score": pt.get("score"),
        "referenced_works_count": w.get("referenced_works_count"),
    }


def stage_works(args):
    author = pick_author(args)
    aid = (author.get("id") or "").rsplit("/", 1)[-1]
    works, cursor, pages = [], "*", 0
    while cursor:
        data = api_get("/works", {
            "filter": f"author.id:{aid}",
            "per_page": 200,
            "cursor": cursor,
            "select": WORK_SELECT,
        }, args.mailto)
        batch = data.get("results") or []
        works.extend(batch)
        pages += 1
        cursor = (data.get("meta") or {}).get("next_cursor")
        print(f"  第 {pages} 页: +{len(batch)} (累计 {len(works)})", file=sys.stderr)
        if not batch:
            break
        if args.limit and len(works) >= args.limit:
            works = works[: args.limit]
            break
        time.sleep(0.2)
    rows = [norm_work(w, aid) for w in works]
    rows.sort(key=lambda r: (r["year"] or 0, r["date"] or ""))
    payload = {
        "stage": "works",
        "query": {"name": args.name, "org": args.org, "field": args.field, "author_id": aid},
        "source": "OpenAlex /works",
        "retrieved_at": now_iso(),
        "author": {
            "openalex_id": aid,
            "name": author.get("display_name"),
            "institutions": inst_names(author),
            "works_count": author.get("works_count"),
            "cited_by_count": author.get("cited_by_count"),
            "h_index": (author.get("summary_stats") or {}).get("h_index"),
            "orcid": author.get("orcid"),
            "topics": author_topics(author, 10),
        },
        "total": len(rows),
        "works": rows,
    }
    out = args.out or f"works_{aid}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"论文 {len(rows)} 条 -> {out}")
    print("下一步: python analyze_works.py --input " + out)
    return payload


def main():
    p = argparse.ArgumentParser(description="学者论文元数据采集（OpenAlex）")
    sub = p.add_subparsers(dest="cmd", required=True)

    for name in ("candidates", "works"):
        sp = sub.add_parser(name)
        sp.add_argument("--name", help="姓名（中文或拼音/英文）")
        sp.add_argument("--org", help="工作单位关键词，用于消歧")
        sp.add_argument("--field", help="所在领域关键词，用于消歧")
        sp.add_argument("--author-id", help="OpenAlex author id，如 A0000000000")
        sp.add_argument("--orcid-id", help="ORCID，如 0000-0002-1825-0097（最精确的消歧方式）")
        sp.add_argument("--mailto", default=os.environ.get("OPENALEX_MAILTO", "audit@example.com"),
                        help="礼貌池邮箱，建议填真实邮箱")
        sp.add_argument("--per-page", type=int, default=25)
        sp.add_argument("--limit", type=int, default=0, help="最多采集论文数，0=不限")
        sp.add_argument("--out", help="输出 JSON 路径")
        sp.add_argument("--auto", action="store_true", help="自动采用首选候选（跳过人工确认，仅限复核）")

    args = p.parse_args()
    if args.cmd == "candidates":
        if not args.name:
            raise SystemExit("--name 必填")
        stage_candidates(args)
    else:
        if not (args.author_id or args.name):
            raise SystemExit("--author-id 或 --name 必填")
        stage_works(args)


if __name__ == "__main__":
    main()
