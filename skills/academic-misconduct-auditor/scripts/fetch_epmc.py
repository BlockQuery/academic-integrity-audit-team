#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过 Europe PMC 公开 API 获取论文元数据、资助信息与开放全文

用法:
  python fetch_epmc.py --works works.json --out epmc
  python fetch_epmc.py --works works.json --out epmc --no-fulltext

为什么用 Europe PMC:
  付费墙论文的 PDF 拿不到，但 Europe PMC 的公开 REST API 会返回
  grantsList（含资助机构与批准号）、以及 PMC 仓库里的开放全文 XML。
  这两样对审计已经够用：基金核查看批准号，数据核查看正文与图表注。
  —— 不需要绕过任何付费墙，全部是公开接口。

合法边界:
  - 只调用 https://www.ebi.ac.uk/europepmc/webservices/rest/ 的公开端点
  - 全文仅下载 isOpenAccess=Y 的条目（PMC 开放子集）
  - 不猜测、不爬取出版社付费页面、不使用任何凭证

输出:
  epmc/epmc_records.json   每篇的 EPMC 记录（含 grantsList、日期、OA 状态）
  epmc/fulltext/*.xml      PMC 开放全文（JATS XML）
  epmc/epmc_summary.md     人读汇总
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
UA = "academic-misconduct-auditor/1.0 (research audit; contact via platform)"


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def get_json(url, retries=4):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last = f"http-{e.code}"
            if e.code == 404:
                return None
            time.sleep(min(2 ** i * 2, 15))
        except Exception as e:
            last = type(e).__name__
            time.sleep(min(2 ** i * 2, 15))
    print(f"  [warn] {last} @ {url[:90]}", file=sys.stderr)
    return None


def get_text(url, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return None
            time.sleep(min(2 ** i * 2, 15))
        except Exception:
            time.sleep(min(2 ** i * 2, 15))
    return None


def parse_jats(xml_bytes):
    """从 JATS XML 里抽审计关心的字段。"""
    out = {
        "funding_texts": [], "award_ids": [], "ethics": [],
        "data_availability": [], "author_contrib": [],
        "received": None, "accepted": None, "n_figs": 0, "n_tables": 0,
        "n_refs": 0, "sections": [],
    }
    try:
        root = ET.fromstring(xml_bytes)
    except Exception:
        return out

    def txt(el):
        return "".join(el.itertext()).strip()

    for fg in root.iter("funding-group"):
        for ag in fg.iter("award-group"):
            src = " ".join(txt(s) for s in ag.iter("funding-source"))
            aid = " ".join(txt(a) for a in ag.iter("award-id"))
            if src or aid:
                out["funding_texts"].append(f"{src} | {aid}".strip(" |"))
            if aid:
                out["award_ids"].extend(re.findall(r"\b(?:[38]\d{7}|[A-Z]{2,}\d{4,})\b", aid))
        for st in fg.iter("funding-statement"):
            out["funding_texts"].append(txt(st))

    for tag in ("ethics", "ethic"):
        for el in root.iter(tag):
            out["ethics"].append(txt(el)[:500])

    for sec in root.iter("sec"):
        title = sec.find("title")
        t = (title.text or "").strip() if title is not None and title.text else ""
        low = t.lower()
        body = txt(sec)[:600]
        if re.search(r"ethic|consent|approval", low):
            out["ethics"].append(body)
        if re.search(r"data availability|availability of data|数据可用", low):
            out["data_availability"].append(body)
        if re.search(r"author contribution|contributorship|作者贡献", low):
            out["author_contrib"].append(body)
        if t:
            out["sections"].append(t[:40])

    for pd in root.iter("pub-date"):
        attr = pd.get("pub-type") or pd.get("date-type") or ""
        y = pd.findtext("year") or ""
        m = pd.findtext("month") or ""
        d = pd.findtext("day") or ""
        val = "-".join(x for x in [y, m.zfill(2) if m else "", d.zfill(2) if d else ""] if x)
        if "receive" in attr.lower():
            out["received"] = val
        elif "accept" in attr.lower():
            out["accepted"] = val

    out["n_figs"] = len(list(root.iter("fig")))
    out["n_tables"] = len(list(root.iter("table-wrap")))
    out["n_refs"] = len(list(root.iter("ref")))
    return out


def main():
    ap = argparse.ArgumentParser(description="Europe PMC 元数据与开放全文获取")
    ap.add_argument("--works", required=True)
    ap.add_argument("--out", default="epmc")
    ap.add_argument("--no-fulltext", action="store_true")
    args = ap.parse_args()

    with open(args.works, "r", encoding="utf-8") as f:
        works = (json.load(f) or {}).get("works") or []
    os.makedirs(args.out, exist_ok=True)
    ft_dir = os.path.join(args.out, "fulltext")
    if not args.no_fulltext:
        os.makedirs(ft_dir, exist_ok=True)

    rows = []
    for i, w in enumerate(works, 1):
        doi = w.get("doi")
        rec = {
            "id": w.get("id"), "year": w.get("year"), "title": w.get("title"),
            "doi": doi, "venue": w.get("venue"),
            "found": False, "pmid": None, "pmcid": None,
            "is_oa": None, "in_pmc": None,
            "grants": [], "fulltext_file": None, "jats": None,
        }
        if not doi:
            rec["note"] = "无 DOI，Europe PMC 无法定位"
            rows.append(rec)
            print(f"[{i}/{len(works)}] skip   无 DOI")
            continue

        q = urllib.parse.urlencode({"query": f'DOI:"{doi}"', "resultType": "core", "format": "json"})
        data = get_json(f"{BASE}/search?{q}")
        res = ((data or {}).get("resultList") or {}).get("result") or []
        if not res:
            rec["note"] = "Europe PMC 未收录"
            rows.append(rec)
            print(f"[{i}/{len(works)}] miss   {doi[:40]}")
            continue

        x = res[0]
        rec.update({
            "found": True,
            "pmid": x.get("pmid"),
            "pmcid": x.get("pmcid"),
            "is_oa": x.get("isOpenAccess"),
            "in_pmc": x.get("inPMC"),
            "pub_type": x.get("pubTypeList", {}).get("pubType"),
            "journal": (x.get("journalInfo") or {}).get("journal", {}).get("title"),
        })
        g = (x.get("grantsList") or {}).get("grant") or []
        rec["grants"] = [
            {"agency": k.get("agency"), "grant_id": k.get("grantId")}
            for k in g if k.get("grantId") or k.get("agency")
        ]

        # 只下 PMC 开放子集的全文
        if not args.no_fulltext and x.get("pmcid") and x.get("isOpenAccess") == "Y":
            xml = get_text(f"{BASE}/{x['pmcid']}/fullTextXML")
            if xml and xml.lstrip().startswith(b"<?xml"):
                fp = os.path.join(ft_dir, f"{x['pmcid']}.xml")
                with open(fp, "wb") as fh:
                    fh.write(xml)
                rec["fulltext_file"] = fp
                rec["jats"] = parse_jats(xml)

        rows.append(rec)
        tag = "PMC" if rec["pmcid"] else "   "
        print(f"[{i}/{len(works)}] {tag} {'G' if rec['grants'] else ' '} {doi[:42]:42} "
              f"{[g['grant_id'] for g in rec['grants']][:2]}")
        time.sleep(0.35)

    total = len(rows)
    payload = {
        "generated_at": now_iso(),
        "source": "Europe PMC REST API (public)",
        "policy": "仅使用公开接口；全文仅下载 isOpenAccess=Y 的 PMC 开放子集。",
        "stats": {
            "total": total,
            "found": sum(1 for r in rows if r["found"]),
            "with_pmcid": sum(1 for r in rows if r["pmcid"]),
            "with_fulltext": sum(1 for r in rows if r["fulltext_file"]),
            "with_grants": sum(1 for r in rows if r["grants"]),
        },
        "items": rows,
    }
    jout = os.path.join(args.out, "epmc_records.json")
    with open(jout, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    L = [f"# Europe PMC 采集汇总\n",
         f"- 生成时间：{payload['generated_at']}",
         f"- 论文 {total} 篇｜EPMC 收录 {payload['stats']['found']}｜有 PMCID {payload['stats']['with_pmcid']}"
         f"｜开放全文已下载 {payload['stats']['with_fulltext']}｜返回资助信息 {payload['stats']['with_grants']}",
         f"- 口径：{payload['policy']}\n",
         "## 资助信息（含付费墙论文，来自公开 API）\n",
         "| 年份 | 论文 | 批准号 | 资助机构 | 全文 |",
         "|---|---|---|---|---|"]
    for r in rows:
        if not r["grants"]:
            continue
        title = (r["title"] or "-").replace("|", "/")[:36]
        ids = "；".join(g["grant_id"] for g in r["grants"] if g.get("grant_id"))
        ag = "；".join(sorted({g["agency"] for g in r["grants"] if g.get("agency")}))[:60]
        L.append(f"| {r['year']} | {title} | {ids} | {ag} | {'XML' if r['fulltext_file'] else '—'} |")

    L.append("\n## 全文可读篇目的结构化字段\n")
    for r in rows:
        j = r.get("jats")
        if not j:
            continue
        L.append(f"### {r['year']} {r['title']}\n")
        L.append(f"- PMCID：{r['pmcid']}｜图表：图 {j['n_figs']} / 表 {j['n_tables']}｜参考文献 {j['n_refs']}")
        if j.get("received") or j.get("accepted"):
            L.append(f"- 收稿 {j.get('received') or '—'}｜接受 {j.get('accepted') or '—'}")
        if j.get("award_ids"):
            L.append(f"- XML 内批准号：{', '.join(sorted(set(j['award_ids']))[:8])}")
        if j.get("ethics"):
            L.append(f"- 伦理声明：{j['ethics'][0][:200]}")
        if j.get("data_availability"):
            L.append(f"- 数据可用性：{j['data_availability'][0][:200]}")
        if j.get("author_contrib"):
            L.append(f"- 作者贡献：{j['author_contrib'][0][:200]}")
        L.append("")

    L.append("## 未收录 / 无 DOI\n")
    for r in rows:
        if not r["found"]:
            L.append(f"- {r['year']} {r['title']}｜DOI {r['doi']}｜{r.get('note')}")

    mout = os.path.join(args.out, "epmc_summary.md")
    with open(mout, "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    s = payload["stats"]
    print(f"\nEPMC 收录 {s['found']}/{s['total']}｜PMC 全文 {s['with_fulltext']}｜资助信息 {s['with_grants']}")
    print(f"记录 -> {jout}\n汇总 -> {mout}")


if __name__ == "__main__":
    main()
