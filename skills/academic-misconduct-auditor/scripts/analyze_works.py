#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""论文元数据指标计算与规则化信号提取

用法:
  python analyze_works.py --input works_A0000000000.json
  python analyze_works.py --input works.json --watchlist watchlist.csv --out-prefix case01

输入:
  --input     fetch_scholar.py works 产出的 JSON
  --watchlist 期刊预警名单 CSV（可选），列: issn,journal,list_name,year,note

输出:
  <prefix>_metrics.json   机器可读指标与信号
  <prefix>_metrics.md     人读摘要（可直接并入报告附录）

重要: 本脚本只产生"信号"，不产生"结论"。每条 signal 都标注了
      证据字段与严重度，最终定性必须由审计人结合原始文献复核。
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import median

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

NSFC_KEYS = ["national natural science foundation", "国家自然科学基金", "nsfc"]
SEV_ORDER = {"high": 0, "watch": 1, "info": 2}


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_watchlist(path):
    if not path:
        return {}
    m = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            issn = (row.get("issn") or "").strip().upper()
            name = (row.get("journal") or "").strip()
            rec = {
                "list_name": (row.get("list_name") or "").strip(),
                "year": (row.get("year") or "").strip(),
                "note": (row.get("note") or "").strip(),
            }
            if issn:
                m[issn] = rec
            if name:
                m[name.lower()] = rec
    return m


def pct(a, b):
    return round(a * 100.0 / b, 1) if b else 0.0


def counter_dict(c, limit=None):
    items = sorted(c.items(), key=lambda kv: -kv[1])
    if limit:
        items = items[:limit]
    return {str(k): v for k, v in items}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--watchlist")
    ap.add_argument("--grants", help="extract_grants.py 的输出，用于按批准号聚合（强烈建议提供）")
    ap.add_argument("--epmc", help="fetch_epmc.py 输出目录，并入付费墙论文的资助号")
    ap.add_argument("--out-prefix")
    args = ap.parse_args()

    data = load(args.input)
    works = data.get("works") or []
    author = data.get("author") or {}
    wl = load_watchlist(args.watchlist)

    grant_nums = {}
    if args.grants and os.path.exists(args.grants):
        gd = load(args.grants) or {}
        for it in gd.get("items") or []:
            raw = (it.get("nsfc_numbers") or []) + (it.get("labeled_numbers") or [])
            nums = list(dict.fromkeys(str(n) for n in raw if n))
            if nums:
                grant_nums[str(it.get("id"))] = nums

    # 并入 works 自带的批准号（中文题录的 Fund 字段、Crossref 回传等），
    # 否则导入的中文成果无法参与按批准号的交叉聚合
    for w in works:
        nums = set(grant_nums.get(str(w.get("id"))) or [])
        for g in (w.get("grants") or []):
            aid = g.get("award_id")
            if aid and re.fullmatch(r"[38]\d{7}|[A-Z]{2,}\d{4,}", str(aid).strip()):
                nums.add(str(aid).strip())
        if nums:
            grant_nums[str(w.get("id"))] = sorted(nums)

    # 并入 Europe PMC 的 grantsList（覆盖付费墙论文，是三个来源里覆盖最广的）
    if args.epmc:
        ep_path = os.path.join(args.epmc, "epmc_records.json") if os.path.isdir(args.epmc) else args.epmc
        if os.path.exists(ep_path):
            ep = load(ep_path) or {}
            for it in ep.get("items") or []:
                nums = set(grant_nums.get(str(it.get("id"))) or [])
                for g in (it.get("grants") or []):
                    gid = str(g.get("grant_id") or "").strip()
                    if not gid:
                        continue
                    for part in re.split(r"[,;，；\s]+", gid):
                        part = part.strip()
                        if re.fullmatch(r"[38]\d{7}|[A-Z]{2,}\d{4,}", part):
                            nums.add(part)
                if nums:
                    grant_nums[str(it.get("id"))] = sorted(nums)

    if not works:
        raise SystemExit("输入中无 works 记录。")

    years = [w["year"] for w in works if w.get("year")]
    by_year = Counter(years)
    y_min, y_max = (min(years), max(years)) if years else (None, None)
    span = (y_max - y_min + 1) if years else 0
    base = median(list(by_year.values())) if by_year else 0

    fields = Counter(w.get("field") for w in works if w.get("field"))
    domains = Counter(w.get("domain") for w in works if w.get("domain"))
    subfields = Counter(w.get("subfield") for w in works if w.get("subfield"))
    venues = Counter(w.get("venue") for w in works if w.get("venue"))
    types = Counter(w.get("type") for w in works if w.get("type"))
    langs = Counter(w.get("language") for w in works if w.get("language"))
    positions = Counter(w.get("my_position") for w in works if w.get("my_position"))
    publishers = Counter(w.get("publisher") for w in works if w.get("publisher"))

    no_doi = [w for w in works if not w.get("doi")]
    no_doi_cn = [w for w in no_doi if (w.get("language") or "").startswith("zh")]
    retracted = [w for w in works if w.get("is_retracted")]
    grant_works = [w for w in works if w.get("grants")]
    nsfc_works = [
        w for w in grant_works
        if any(k in (g.get("funder") or "").lower() for g in w["grants"] for k in NSFC_KEYS)
    ]
    grant_counts = [len(w.get("grants") or []) for w in works]
    stacked = [w for w in works if len(w.get("grants") or []) >= 3]

    coauthors = Counter()
    for w in works:
        for c in w.get("coauthors") or []:
            coauthors[c] += 1

    top_field, top_field_n = (fields.most_common(1)[0] if fields else (None, 0))
    top_domain, top_domain_n = (domains.most_common(1)[0] if domains else (None, 0))
    topics = Counter(w.get("topic") for w in works if w.get("topic"))

    signals = []

    def add(sid, dim, severity, title, detail, evidence):
        signals.append({
            "id": sid, "dimension": dim, "severity": severity,
            "title": title, "detail": detail, "evidence": evidence[:12],
        })

    # --- D0 身份与画像一致性（防止把他人成果算到目标头上） ---
    # S0 仅在同一数据源内部判定：导入的中文题录已经过姓名匹配确认本人署名，
    # 其合作者与英文论文天然是两套人，跨源比较会必然产生假阳性。
    d0_pool = [w for w in works if w.get("source") != "cnki-import"]
    coauthor_sets = {w["id"]: set(w.get("coauthors") or []) for w in d0_pool}
    subfield_sets = {w["id"]: (w.get("subfield"), w.get("field")) for w in d0_pool}
    isolated = []
    if len(d0_pool) >= 4:
        for w in d0_pool:
            mine = coauthor_sets[w["id"]]
            others = [coauthor_sets[o["id"]] for o in d0_pool if o["id"] != w["id"]]
            overlaps = [len(mine & o) for o in others]
            max_overlap = max(overlaps) if overlaps else 0
            same_track = any(
                subfield_sets[o["id"]][0] == subfield_sets[w["id"]][0]
                for o in d0_pool if o["id"] != w["id"]
            )
            if mine and max_overlap == 0 and not same_track:
                isolated.append(w)
        if isolated:
            add("S0-identity-suspect", "D0", "high",
                f"{len(isolated)} 篇论文与其余成果无合作者交集且学科不重叠，疑似被误并入该作者档案",
                "OpenAlex 的作者消歧存在错误合并。这些论文可能属于同名他人，在核验原始文献前不得计入本人成果，否则会得出错误的'跨专业'结论。",
                [f"{w['year']} {w.get('title')}｜{w.get('venue')}｜DOI {w.get('doi')}" for w in isolated])
    inst_timeline = defaultdict(set)
    for w in works:
        if w.get("year"):
            for i in (w.get("my_institutions") or []):
                inst_timeline[w["year"]].add(i)
    switch_years = {y: sorted(v) for y, v in sorted(inst_timeline.items()) if len(v) >= 3}
    if switch_years:
        add("S0-inst-switch", "D0", "info",
            f"{len(switch_years)} 个年度出现 ≥3 个署名单位",
            "多头署名在临床合作中常见（附属医院+学院+合作实验室）。仅作为身份核对与经历核对的线索，不构成问题。",
            [f"{y}: {'、'.join(list(v)[:3])}" for y, v in list(switch_years.items())[-5:]])

    # --- D1 产出节奏 ---
    if by_year:
        peak_year, peak_n = max(by_year.items(), key=lambda kv: kv[1])
        if peak_n >= 5 and base and peak_n >= base * 3:
            add("S1-peak-burst", "D1", "watch",
                f"产出尖峰 {peak_year} 年 {peak_n} 篇（年均中位 {base:g}）",
                "同一年度产出陡增，可能来自团队集中投稿、职称/项目考核冲刺，也可能涉及成果注水，需逐篇核对投稿与录用时间。",
                [f"{w['year']} {w.get('venue')}" for w in works if w["year"] == peak_year])
        gaps = [y for y in range(y_min, y_max + 1) if by_year.get(y, 0) == 0]
        if len(gaps) >= 3 and span >= 6:
            add("S1-gap", "D1", "info",
                f"存在 {len(gaps)} 个无发表年份：{gaps[0]}–{gaps[-1]} 区间内断续空白",
                "产出中断常见于岗位变动、临床任务或数据积累期，本身不构成异常，仅作为履历连贯性核对线索。", gaps)
        if span and len(works) / span >= 8:
            add("S1-density", "D1", "watch",
                f"年均 {len(works)/span:.1f} 篇，密度偏高（跨度 {span} 年，共 {len(works)} 篇）",
                "高产本身不等于不端。需结合团队规模、作者位次、研究类型（综述/临床/基础）判断。",
                [f"{w['year']} {w.get('title')}" for w in works[-6:]])

    # --- D2 专业相关性 ---
    # 口径说明: OpenAlex 的 field 粒度偏粗（临床示例学科研究常被判为 Medicine），
    # 因此以一级 domain 作为"是否跨学科"的主基准，field/subfield/topic 仅作解释层。
    if top_domain and len(works) >= 5:
        off_domain = [w for w in works if w.get("domain") and w["domain"] != top_domain]
        off_ratio = pct(len(off_domain), len(works))
        if off_ratio >= 30:
            add("S2-domain-drift", "D2", "watch",
                f"主学科域外论文占 {off_ratio}%（主域：{top_domain}，{top_domain_n}/{len(works)} 篇）",
                "跨一级学科域发文本身不构成问题：示例学科×材料、示例学科×影像算法属常见交叉。需判断是否存在可解释的技术主线，以及在跨域论文中本人是主导还是挂名。",
                [f"{w['year']} [{w.get('domain')}/{w.get('field')}] {w.get('title')}" for w in off_domain[-10:]])
        if len(domains) >= 3:
            add("S2-domain-cross", "D2", "info",
                f"横跨 {len(domains)} 个一级学科域：{'、'.join(list(domains)[:5])}",
                "域数量多说明成果面宽。结合下方 topic 清单判断是否为一条主线（如'颅面影像'串起示例学科/影像/算法），还是彼此无关的拼盘。",
                list(domains)[:6])
    if top_field and len(works) >= 8 and fields.get(top_field, 0) <= len(works) * 0.3:
        add("S2-field-scatter", "D2", "info",
            f"最大单一 field 仅占 {pct(fields.get(top_field,0), len(works))}%（{top_field}）",
            "学科标签分散。OpenAlex 对中文临床期刊的分类粗糙，此项应视为分类噪声而非异常，须以论文实际内容判断。", list(fields)[:6])

    # --- D3 期刊质量 ---
    if venues:
        v, vn = venues.most_common(1)[0]
        if len(works) >= 6 and pct(vn, sum(venues.values())) >= 40:
            add("S3-venue-concentration", "D3", "watch",
                f"单刊集中度 {pct(vn, sum(venues.values()))}%：{v}（{vn} 篇）",
                "高度依赖单一期刊，需核查该刊收录状态、版面费、审稿周期与自引率。", [v])
        top2 = venues.most_common(2)
        if len(works) >= 8 and len(top2) == 2 and pct(top2[0][1] + top2[1][1], sum(venues.values())) >= 60:
            add("S3-venue-top2", "D3", "info",
                f"前两本期刊占 {pct(top2[0][1]+top2[1][1], sum(venues.values()))}%",
                "发文渠道集中，便于批量操作，需核对两刊的同行评审记录与伦理审批材料。",
                [f"{k}（{v} 篇）" for k, v in top2])
    hits = []
    for w in works:
        for key in [(w.get("issn") or "").upper(), (w.get("venue") or "").lower()]:
            if key and key in wl:
                hits.append((w, wl[key]))
                break
    if hits:
        add("S3-watchlist", "D3", "high",
            f"命中期刊预警/观察名单 {len(hits)} 篇",
            "名单来源与年份见 watchlist 文件。预警名单仅代表该刊存在质量或规范风险，不等同于单篇论文造假。",
            [f"{w.get('year')} {w.get('venue')}｜{(rec.get('list_name') or '')} {rec.get('year') or ''}" for w, rec in hits])

    # --- D4 学术规范 ---
    if retracted:
        add("S4-retraction", "D4", "high",
            f"检出撤稿记录 {len(retracted)} 篇",
            "撤稿原因是定性的核心：数据造假、图片重复、重复发表、作者同意问题，性质差异极大。必须取 Retraction Watch / 期刊撤稿声明原文。",
            [f"{w['year']} {w.get('title')}｜DOI {w.get('doi')}" for w in retracted])
    if no_doi:
        ratio = pct(len(no_doi), len(works))
        if ratio >= 40 and len(works) >= 5:
            add("S4-missing-doi", "D4", "info",
                f"{ratio}% 论文无 DOI（{len(no_doi)}/{len(works)}）",
                "中文期刊在 OpenAlex 的 DOI 覆盖不全，此项多为数据库盲区而非论文问题。须用知网/万方补检后再判断。",
                [f"{w['year']} {w.get('title')}" for w in no_doi[:10]])
    if len(coauthors) <= 5 and len(works) >= 10:
        add("S4-narrow-network", "D4", "watch",
            f"合作者高度集中：{len(coauthors)} 位不同合作者支撑 {len(works)} 篇",
            "封闭作者圈子是论文工厂与合作代写的常见特征之一，但小团队独立研究同样如此，不能单独定性。",
            [f"{k}（{v} 篇）" for k, v in coauthors.most_common(8)])
    mid = positions.get("middle") or 0
    if len(works) >= 8 and pct(mid, sum(positions.values() or [1])) >= 60:
        add("S4-middle-author", "D4", "watch",
            f"中间作者位次占 {pct(mid, sum(positions.values()))}%",
            "长期非一作/非通讯，提示贡献以参与为主。若同时用于职称或项目结题的'主持成果'，需核对贡献声明。",
            [f"{w['year']} {w.get('title')}" for w in works if w.get("my_position") == "middle"][:10])
    mid_multi = [w for w in works if w.get("my_position") == "middle" and (w.get("n_authors") or 0) >= 3]
    if mid_multi:
        add("S4-position-caveat", "D4", "info",
            f"{len(mid_multi)} 篇被标为「中间作者」，其中可能包含共同第一作者",
            "**这是本套元数据最不可靠的字段之一。** OpenAlex 的 author_position 只区分 first/middle/last，"
            "共同第一作者常被归为 middle。在判断'本人是否主导'之前，必须打开原文看署名标注"
            "（如姓名后的 # / * 号、脚注 'These authors contributed equally'）。"
            "仅凭此字段得出'参与型署名、不构成问题'，是本类审计最典型的假阴性来源。",
            [f"{w['year']} {w.get('title')}" for w in mid_multi[:8]])

    # --- D5 基金合规 ---
    if grant_works:
        add("S5-grant-coverage", "D5", "info",
            f"{len(grant_works)}/{len(works)} 篇有基金标注，其中 NSFC 相关 {len(nsfc_works)} 篇",
            "元数据中的 funder 字段由出版商或 Crossref 提供，标注错误与元数据缺失都会造成误判，须以论文 PDF 首页脚注（Acknowledgments/Funding）原文为准。",
            [f"{w['year']} {w.get('venue')}" for w in nsfc_works[:10]])
    if nsfc_works and len(nsfc_works) < len(grant_works):
        add("S5-nsfc-partial", "D5", "info",
            f"存在非 NSFC 基金标注的论文 {len(grant_works)-len(nsfc_works)} 篇",
            "多源资助属正常。核查重点是：标注的基金号是否真实存在、是否在项目执行期内、研究内容是否属于该项目任务书范围。", [])
    if stacked:
        add("S5-grant-stacking", "D5", "watch",
            f"{len(stacked)} 篇单篇标注 ≥3 个基金",
            "多基金拼接标注常见于团队合作，也可能是一篇成果重复交账。需把同一篇论文与多个项目的结题报告逐一比对。",
            [f"{w['year']} {w.get('title')}｜{len(w['grants'])} 个基金" for w in stacked])
    award_ids = Counter()
    for w in nsfc_works:
        for g in w["grants"]:
            if any(k in (g.get("funder") or "").lower() for k in NSFC_KEYS) and g.get("award_id"):
                award_ids[g["award_id"]] += 1
    if award_ids:
        add("S5-award-ids", "D5", "info",
            f"NSFC 类基金号 {len(award_ids)} 个",
            "拿这些号码去基金委科学基金共享服务网核对：项目负责人、依托单位、起止年月、资助类别。负责人或单位不符即为高风险线索。",
            [f"{k}（{v} 篇）" for k, v in award_ids.most_common(10)])

    # --- D5 交叉核查：同一基金是否标注了分属不同领域的论文 ---
    # 「标注无关项目成果」是基金类案件的核心形态。聚合粒度必须落到批准号，
    # 按资助机构名聚合会把同一机构的不同项目混为一谈，属严重误报。
    funder_map = defaultdict(list)
    number_map = defaultdict(list)
    for w in works:
        nums = grant_nums.get(str(w.get("id"))) or []
        if nums:
            for n in nums:
                number_map[n].append(w)
        else:
            seen_f = set()
            for g in (w.get("grants") or []):
                f = g.get("funder")
                if f and f not in seen_f:
                    seen_f.add(f)
                    funder_map[f].append(w)

    def _cross_check(groups, id_prefix, dim, sev, label):
        for key, ws in groups.items():
            if len(ws) < 2:
                continue
            fields_in = Counter(x.get("field") for x in ws if x.get("field"))
            if len(fields_in) < 2:
                continue
            top_share = pct(fields_in.most_common(1)[0][1], sum(fields_in.values()))
            if top_share < 70 or len(fields_in) >= 3:
                add(f"S5-cross-topic-{id_prefix}" if id_prefix else "S5-cross-topic",
                    dim, sev,
                    f"{label}「{key}」挂载 {len(ws)} 篇、横跨 {len(fields_in)} 个学科领域的论文",
                    "这是「标注无关项目成果」的典型形态，但**信号不等于结论**：大型交叉项目也可能跨领域。"
                    "必须打开该项目的研究内容（结案报告摘要或任务书关键词），逐篇比对论文主题是否属于其范围。"
                    "判据不是学科标签是否一致，而是「这篇论文的研究内容，是否可能是该项目承诺要做的事」。",
                    [f"{x['year']} [{x.get('field') or '?'}] {(x.get('title') or '')[:70]}" for x in ws])

    _cross_check(number_map, "", "D5", "high", "批准号")
    if funder_map:
        big = {k: v for k, v in funder_map.items() if len(v) >= 3}
        if big:
            add("S5-funder-unverified", "D5", "info",
                f"{len(big)} 个资助机构名下有 ≥3 篇论文未提取到批准号",
                "当前只能按机构名聚合，无法判断是否属于同一项目——**粒度不足，不能据此定性**。"
                "先跑 extract_grants.py 从全文提取批准号，再按批准号重新聚合。",
                [f"{k}（{len(v)} 篇）" for k, v in big.items()])

    # --- D6 成果一致性 ---
    if types:
        art = types.get("article") or 0
        if len(works) >= 8 and pct(art, len(works)) < 50:
            add("S6-type-mix", "D6", "info",
                f"正式论文（article）占比 {pct(art, len(works))}%，其余为 {'、'.join(f'{k}:{v}' for k,v in types.items() if k!='article')}",
                "会议摘要、社论、勘误等计入个人成果清单会放大产出规模，核对履历表时须按类型拆分。", [])

    coverage = [
        "OpenAlex 对中文期刊（尤其非核心刊）收录不完整，中文成果必须另用知网/万方/维普补检。",
        "funder/grants 字段依赖出版商回传，存在漏标与错标，基金合规须以论文原文脚注核对。",
        "撤稿状态依赖 Retraction Watch 同步，存在滞后，须交叉核对期刊官网与 PubPeer。",
        "本脚本不判断'代写''论文工厂'——这两项无法由元数据证明，只能由图片复用、文本相似度、审稿周期、原始数据可得性等证据链推断。",
    ]

    metrics = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "input_file": args.input,
        "author": author,
        "coverage_warning": coverage,
        "summary": {
            "total_works": len(works),
            "year_range": [y_min, y_max],
            "span_years": span,
            "avg_per_year": round(len(works) / span, 2) if span else None,
            "median_per_year": base,
            "distinct_venues": len(venues),
            "distinct_coauthors": len(coauthors),
            "total_citations": sum((w.get("cited_by") or 0) for w in works),
            "retracted": len(retracted),
            "nsfc_flagged": len(nsfc_works),
            "oa_ratio": pct(sum(1 for w in works if w.get("is_oa")), len(works)),
            "no_doi_ratio": pct(len(no_doi), len(works)),
            "no_doi_ratio_zh": pct(len(no_doi_cn), len([w for w in works if (w.get("language") or "").startswith("zh")]) or 0),
        },
        "distributions": {
            "by_year": dict(sorted(by_year.items())),
            "by_field": counter_dict(fields),
            "by_subfield": counter_dict(subfields, 12),
            "by_domain": counter_dict(domains),
            "by_venue": counter_dict(venues, 20),
            "by_publisher": counter_dict(publishers, 10),
            "by_position": counter_dict(positions),
            "by_type": counter_dict(types),
            "by_language": counter_dict(langs),
            "by_topic": counter_dict(topics, 40),
        },
        "grant_audit": {
            "works_with_grant": len(grant_works),
            "nsfc_works": len(nsfc_works),
            "max_grants_on_one_paper": max(grant_counts) if grant_counts else 0,
            "award_ids": counter_dict(award_ids),
            "funders": counter_dict(Counter(g.get("funder") for w in grant_works for g in w["grants"] if g.get("funder")), 15),
        },
        "identity_check": {
            "isolated_count": len(isolated),
            "isolated_work_ids": [w["id"] for w in isolated],
            "isolated_titles": [f"{w.get('year')} {w.get('title')}" for w in isolated],
            "institution_timeline": {str(y): sorted(v) for y, v in sorted(inst_timeline.items())},
            "note": "isolated 论文在核验原文前应排除出统计口径，否则会污染'专业跨度'与'产出量'两项指标。",
        },
        "signals": sorted(signals, key=lambda s: SEV_ORDER.get(s["severity"], 9)),
    }

    prefix = args.out_prefix or "audit"
    jout = f"{prefix}_metrics.json"
    with open(jout, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    L = []
    a = author or {}
    L.append(f"# 论文元数据指标摘要\n")
    L.append(f"- 对象：{a.get('name','-')}（{a.get('openalex_id','-')}）")
    L.append(f"- 机构：{'、'.join(a.get('institutions') or []) or '-'}")
    L.append(f"- 采集时间：{metrics['generated_at']}　数据源：OpenAlex")
    L.append(f"- 论文 {len(works)} 篇，{y_min}–{y_max}（{span} 年），年均 {metrics['summary']['avg_per_year']}，"
             f"被引合计 {metrics['summary']['total_citations']}，期刊 {len(venues)} 种，合作者 {len(coauthors)} 人")
    L.append(f"- 撤稿 {len(retracted)}｜NSFC 标注 {len(nsfc_works)} 篇｜OA 占比 {metrics['summary']['oa_ratio']}%｜无 DOI {metrics['summary']['no_doi_ratio']}%\n")
    L.append("## 年度分布\n")
    L.append("| 年份 | " + " | ".join(str(y) for y in sorted(by_year)) + " |")
    L.append("|---|" + "---|" * len(by_year))
    L.append("| 篇数 | " + " | ".join(str(by_year[y]) for y in sorted(by_year)) + " |\n")
    L.append("## 学科分布\n")
    L.append("| 一级域 | 篇数 | 占比 |")
    L.append("|---|---|---|")
    for d, n in domains.most_common():
        L.append(f"| {d} | {n} | {pct(n, len(works))}% |")
    L.append("")
    L.append("## 主题分布（判断是否存在技术主线）\n")
    L.append("| 主题 | 篇数 |")
    L.append("|---|---|")
    for t, n in topics.most_common(15):
        L.append(f"| {t} | {n} |")
    L.append("")
    L.append("## 论文清单（按年份倒序）\n")
    L.append("| 年份 | 标题 | 期刊 | 位次 | 基金 | DOI |")
    L.append("|---|---|---|---|---|---|")
    for w in sorted(works, key=lambda x: (x.get("year") or 0, x.get("date") or ""), reverse=True):
        title = (w.get("title") or "-").replace("|", "/")[:60]
        venue = (w.get("venue") or "-").replace("|", "/")[:28]
        pos = w.get("my_position") or "-"
        if w.get("is_corresponding"):
            pos += "/通讯"
        g = len(w.get("grants") or [])
        L.append(f"| {w.get('year')} | {title} | {venue} | {pos} | {g or ''} | {w.get('doi') or '—'} |")
    L.append("")
    L.append("## 信号清单\n")
    if not signals:
        L.append("未触发任何规则化信号。注意：规则未触发 ≠ 无问题，仅表示元数据层面无异常。")
    for s in metrics["signals"]:
        L.append(f"### [{s['severity'].upper()}] {s['id']}（{s['dimension']}）{s['title']}")
        L.append(s["detail"])
        if s["evidence"]:
            L.append("证据：")
            for e in s["evidence"]:
                L.append(f"- {e}")
        L.append("")
    L.append("## 数据盲区\n")
    for c in coverage:
        L.append(f"- {c}")

    mout = f"{prefix}_metrics.md"
    with open(mout, "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    print(f"指标 -> {jout}\n摘要 -> {mout}")
    print(f"信号 {len(signals)} 条：" + "、".join(f"{s['id']}({s['severity']})" for s in metrics["signals"]))


if __name__ == "__main__":
    main()
