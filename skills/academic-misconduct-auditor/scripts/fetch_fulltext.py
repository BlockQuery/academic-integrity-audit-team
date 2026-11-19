#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多渠道合法全文获取（阶梯式，能拿的全拿，拿不到的出购买清单）

用法:
  python fetch_fulltext.py --input works.json --out-dir fulltext
  python fetch_fulltext.py --input works_cn.csv --out-dir fulltext      # CSV: title,venue,year,doi,...
  UNPAYWALL_EMAIL=you@org.edu python fetch_fulltext.py --input works.json --out-dir fulltext

渠道阶梯（逐篇、逐渠道尝试，拿到即停）:
  1 openalex   OpenAlex 全部 locations（不只 best_oa_location）；无 DOI 时按标题检索
  2 unpaywall  Unpaywall（需环境变量 UNPAYWALL_EMAIL，未设置则跳过，不用任何默认邮箱）
  3 s2         Semantic Scholar openAccessPdf
  4 epmc       Europe PMC：有 PMC 副本取 JATS XML（比 PDF 更适合审计）
  5 arxiv      arXiv DOI 直链
  6 journal    references/journal_sites.json 登记的"官网免费摘要/全文 PDF"期刊站点（可扩充）
  7 fallback   以上全失败 -> 写入 purchase_list.md：知网/万方/NSTL 检索链接 + 文献传递信息

合规边界（不可放宽）:
  - 只访问公开可直接下载的资源。不用 Sci-Hub 及任何镜像，不借账号，不伪造 cookie/referer
    以绕过鉴权，遇到 401/402/403 即视为付费墙并停止该渠道，不重试、不换 UA 硬闯
  - 每份文件记录 source_channel / url / license / sha256 / 获取时间，报告必须据此标注来源
  - 获取到的"摘要 PDF"只记 level=abstract，不得在报告里当全文使用

输出:
  <out-dir>/*.pdf|*.xml            已获取文件
  <out-dir>/fulltext_manifest.json 机器可读清单
  <out-dir>/fulltext_manifest.md   人读清单 + 分渠道获取率
  <out-dir>/purchase_list.md       未获取篇目的合法补取清单（按刊分组）
"""

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 academic-audit/2.0")
MIN_BYTES = 12 * 1024
MAX_BYTES = 40 * 1024 * 1024
ARXIV_DOI = re.compile(r"10\.48550/arxiv\.([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)", re.I)
HERE = os.path.dirname(os.path.abspath(__file__))
SITES_JSON = os.path.join(HERE, "..", "references", "journal_sites.json")
BLOCKED = (401, 402, 403)


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def clean_doi(s):
    s = (s or "").strip()
    s = re.sub(r"^https?://(dx\.)?doi\.org/", "", s, flags=re.I)
    return s if s.startswith("10.") else None


def http(url, accept="application/json", timeout=30, retries=3):
    """返回 (bytes, ctype, err)。403 等付费墙信号不重试。"""
    last = "unknown"
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read(MAX_BYTES + 1), (r.headers.get("Content-Type") or "").lower(), None
        except urllib.error.HTTPError as e:
            last = f"http-{e.code}"
            if e.code in BLOCKED or e.code == 404:
                return None, "", ("paywalled-or-blocked" if e.code in BLOCKED else last)
            time.sleep(min(2 ** a * 2, 15))
        except Exception as e:
            last = type(e).__name__
            time.sleep(min(2 ** a * 2, 15))
    return None, "", f"failed:{last}"


def jget(url):
    data, _, err = http(url)
    if not data:
        return None
    try:
        return json.loads(data.decode("utf-8"))
    except Exception:
        return None


def get_pdf(url, referer=None):
    """下载并校验 PDF。返回 (bytes, err)。"""
    try:
        h = {"User-Agent": UA, "Accept": "application/pdf,*/*"}
        if referer:
            h["Referer"] = referer
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=75) as r:
            data = r.read(MAX_BYTES + 1)
            ctype = (r.headers.get("Content-Type") or "").lower()
    except urllib.error.HTTPError as e:
        return None, "paywalled-or-blocked" if e.code in BLOCKED else f"http-{e.code}"
    except Exception as e:
        return None, f"failed:{type(e).__name__}"
    if len(data) > MAX_BYTES:
        return None, "too-large"
    if not data.startswith(b"%PDF-"):
        return None, f"not-pdf({ctype[:30]})"
    if len(data) < MIN_BYTES:
        return None, f"too-small({len(data)}B)"
    return data, None


# ---------------------------------------------------------------- 渠道实现
# 每个渠道返回候选列表 [(channel, url, license, kind)]，kind: pdf|xml

def ch_openalex(w):
    out, doi = [], w["doi"]
    if doi:
        j = jget("https://api.openalex.org/works/doi:" + urllib.parse.quote(doi))
    else:
        t = w["title"]
        j = None
        if t:
            r = jget("https://api.openalex.org/works?per-page=1&search=" + urllib.parse.quote(t[:200]))
            res = (r or {}).get("results") or []
            # 标题检索必须严格相等才采信，避免张冠李戴
            if res and re.sub(r"\W", "", (res[0].get("title") or "")).lower() == re.sub(r"\W", "", t).lower():
                j = res[0]
    if not j:
        return out
    w.setdefault("_oa_status", (j.get("open_access") or {}).get("oa_status"))
    locs = list(j.get("locations") or [])
    if j.get("best_oa_location"):
        locs.insert(0, j["best_oa_location"])
    for L in locs:
        if L.get("is_oa") and L.get("pdf_url"):
            out.append(("openalex", L["pdf_url"], L.get("license"), "pdf"))
    return out


def ch_unpaywall(w):
    email = os.environ.get("UNPAYWALL_EMAIL")
    if not email or not w["doi"]:
        return []
    j = jget(f"https://api.unpaywall.org/v2/{urllib.parse.quote(w['doi'])}?email={urllib.parse.quote(email)}")
    out = []
    for L in ([(j or {}).get("best_oa_location")] + list((j or {}).get("oa_locations") or [])):
        if L and L.get("url_for_pdf"):
            out.append(("unpaywall", L["url_for_pdf"], L.get("license"), "pdf"))
    return out


def ch_s2(w):
    if not w["doi"]:
        return []
    j = jget("https://api.semanticscholar.org/graph/v1/paper/DOI:" +
             urllib.parse.quote(w["doi"]) + "?fields=openAccessPdf")
    p = (j or {}).get("openAccessPdf") or {}
    return [("s2", p["url"], p.get("license"), "pdf")] if p.get("url") else []


def ch_epmc(w):
    if not w["doi"]:
        return []
    q = urllib.parse.quote(f'DOI:"{w["doi"]}"')
    j = jget(f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={q}&resultType=core&format=json")
    res = ((j or {}).get("resultList") or {}).get("result") or []
    if not res:
        return []
    r = res[0]
    w["_epmc_grants"] = [g.get("grantId") for g in ((r.get("grantsList") or {}).get("grant") or []) if g.get("grantId")]
    pmcid = r.get("pmcid")
    if pmcid and r.get("inPMC") == "Y":
        return [("epmc-xml", f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML",
                 r.get("license"), "xml")]
    return []


def ch_arxiv(w):
    m = ARXIV_DOI.search(w["doi"] or "")
    return [("arxiv", f"https://arxiv.org/pdf/{m.group(1)}", "arXiv", "pdf")] if m else []


def load_sites():
    try:
        with open(SITES_JSON, "r", encoding="utf-8") as f:
            return json.load(f).get("sites", [])
    except Exception:
        return []


def ch_journal(w, sites):
    """已登记期刊官网：按 pdf_pattern 直链（若登记了）。未登记的刊只在 purchase_list 里给入口。"""
    out = []
    for s in sites:
        if any(k in (w["venue"] or "") for k in s.get("match", [])) and s.get("direct_pdf_regex_page"):
            # 仅当站点登记了"详情页 -> PDF 正则"时才尝试；详情页 URL 需在登记里给出模板
            tpl = s.get("detail_url_template")
            if not tpl:
                continue
            page = tpl.format(year=w["year"], title=urllib.parse.quote(w["title"] or ""))
            data, _, err = http(page, accept="text/html")
            if not data:
                continue
            html = data.decode("utf-8", "ignore")
            for m in re.finditer(s["direct_pdf_regex_page"], html):
                out.append(("journal:" + s["name"], urllib.parse.urljoin(page, m.group(1)),
                            s.get("license", "journal-free-access"), "pdf"))
    return out


# ---------------------------------------------------------------- 输入与落盘

def load_works(path):
    ext = os.path.splitext(path)[1].lower()
    rows = []
    if ext == ".csv":
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    else:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        rows = payload.get("works") if isinstance(payload, dict) else payload
    works = []
    for i, r in enumerate(rows or [], 1):
        works.append({
            "id": r.get("id") or r.get("no") or f"w{i:03d}",
            "year": str(r.get("year") or "0000"),
            "title": (r.get("title") or "").strip(),
            "doi": clean_doi(r.get("doi")),
            "venue": (r.get("venue") or r.get("journal") or "").strip(),
            "volume": r.get("volume") or "", "issue": r.get("issue") or "", "pages": r.get("pages") or "",
            "authors": r.get("authors") or "",
            "pdf_url": r.get("pdf_url"), "oa_url": r.get("oa_url"),
        })
    return works


def stem_of(w):
    wid = re.sub(r"[^A-Za-z0-9]", "", str(w["id"]))[:12] or "x"
    return f"{w['year']}_{wid}"


def purchase_links(w):
    q = urllib.parse.quote(w["title"])
    d = [f"- 知网检索：https://kns.cnki.net/kns8s/defaultresult/index?kw={q}",
         f"- 万方检索：https://s.wanfangdata.com.cn/paper?q={q}",
         f"- NSTL 文献传递：https://www.nstl.gov.cn/ （检索篇名后选「文献传递」，约 3–10 元/篇）",
         "- 单位图书馆文献传递 / CALIS 馆际互借（填：篇名、刊名、年卷期页）"]
    if w["doi"]:
        d.insert(0, f"- DOI 落地页：https://doi.org/{w['doi']}")
    return d


def main():
    ap = argparse.ArgumentParser(description="多渠道合法全文获取")
    ap.add_argument("--input", required=True, help="works.json 或含 title/venue/year/doi 列的 CSV")
    ap.add_argument("--out-dir", default="fulltext")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-title-search", action="store_true", help="无 DOI 篇目不按标题检索")
    args = ap.parse_args()

    works = load_works(args.input)
    if args.limit:
        works = works[: args.limit]
    os.makedirs(args.out_dir, exist_ok=True)
    sites = load_sites()
    if not os.environ.get("UNPAYWALL_EMAIL"):
        print("提示：未设置 UNPAYWALL_EMAIL，跳过 Unpaywall 渠道（建议用单位邮箱设置后重跑）")

    rows, started = [], time.time()
    for i, w in enumerate(works, 1):
        stem = stem_of(w)
        rec = {"id": w["id"], "year": w["year"], "title": w["title"], "doi": w["doi"],
               "venue": w["venue"], "file": None, "status": "pending", "level": None,
               "source_channel": None, "url": None, "license": None,
               "bytes": None, "sha256": None, "fetched_at": None, "tried": []}

        cached = [os.path.join(args.out_dir, stem + e) for e in (".pdf", ".xml")]
        hit = next((c for c in cached if os.path.exists(c) and os.path.getsize(c) > MIN_BYTES // 4), None)
        if hit:
            blob = open(hit, "rb").read()
            rec.update(file=hit, status="cached", level="fulltext", bytes=len(blob),
                       sha256=hashlib.sha256(blob).hexdigest()[:16])
            rows.append(rec)
            print(f"[{i}/{len(works)}] cached  {stem}")
            continue

        cands = []
        if w.get("pdf_url"):
            cands.append(("input-pdf", w["pdf_url"], None, "pdf"))
        if not (args.no_title_search and not w["doi"]):
            for fn in (ch_openalex, ch_unpaywall, ch_s2, ch_epmc, ch_arxiv):
                try:
                    cands += fn(w)
                except Exception as e:
                    rec["tried"].append(f"{fn.__name__}:{type(e).__name__}")
                time.sleep(0.25)
        try:
            cands += ch_journal(w, sites)
        except Exception as e:
            rec["tried"].append(f"journal:{type(e).__name__}")

        seen, uniq = set(), []
        for c in cands:
            if c[1] not in seen:
                seen.add(c[1])
                uniq.append(c)

        for ch, url, lic, kind in uniq:
            if kind == "xml":
                data, ctype, err = http(url, accept="application/xml", timeout=60)
                ok = bool(data) and len(data) > 2000 and b"<article" in data[:4000]
                err = None if ok else (err or "not-jats")
                ext = ".xml"
            else:
                data, err = get_pdf(url)
                ext = ".pdf"
            rec["tried"].append(f"{ch}:{'OK' if data and not err else err}")
            if data and not err:
                path = os.path.join(args.out_dir, stem + ext)
                with open(path, "wb") as fh:
                    fh.write(data)
                rec.update(file=path, status="downloaded", level="fulltext", source_channel=ch,
                           url=url, license=lic, bytes=len(data),
                           sha256=hashlib.sha256(data).hexdigest()[:16], fetched_at=now_iso())
                break
        if rec["status"] != "downloaded":
            rec["status"] = "not-obtained" if uniq else "no-oa-copy"
        rows.append(rec)
        tag = f"OK <- {rec['source_channel']}" if rec["status"] == "downloaded" else rec["status"]
        print(f"[{i}/{len(works)}] {tag:28s} {stem}  {w['title'][:24]}")

    total = len(works)
    got = [r for r in rows if r["status"] in ("downloaded", "cached")]
    by_ch = {}
    for r in got:
        k = r["source_channel"] or "cached"
        by_ch[k] = by_ch.get(k, 0) + 1
    manifest = {
        "generated_at": now_iso(), "input": args.input,
        "policy": "仅公开可直接下载的资源；不使用盗版镜像、不借账号、不绕鉴权；每份记录来源渠道与许可。",
        "elapsed_sec": round(time.time() - started, 1),
        "stats": {"requested": total, "obtained": len(got), "missing": total - len(got),
                  "success_rate": round(len(got) * 100.0 / total, 1) if total else 0.0, "by_channel": by_ch},
        "items": rows,
    }
    with open(os.path.join(args.out_dir, "fulltext_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    L = ["# 全文获取清单\n", f"- 生成时间：{manifest['generated_at']}",
         f"- 请求 {total} 篇，获取 {len(got)} 篇（{manifest['stats']['success_rate']}%）",
         f"- 分渠道：{json.dumps(by_ch, ensure_ascii=False)}",
         "- 口径：仅合法公开渠道，不绕付费墙\n",
         "| 年份 | 论文 | 状态 | 渠道 | 许可 | 大小 |", "|---|---|---|---|---|---|"]
    for r in rows:
        size = f"{r['bytes']//1024}KB" if r.get("bytes") else ""
        L.append(f"| {r['year']} | {(r['title'] or '-').replace('|','/')[:40]} | {r['status']} | "
                 f"{r.get('source_channel') or ''} | {r.get('license') or ''} | {size} |")
    with open(os.path.join(args.out_dir, "fulltext_manifest.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    miss = [(r, w) for r, w in zip(rows, works) if r["status"] not in ("downloaded", "cached")]
    P = ["# 未获取篇目：合法补取清单\n",
         f"共 {len(miss)} 篇。报告中这些篇目须标注「全文未获取，相关维度无法核查（D）」。",
         "知网单篇约 0.5–3 元；中华医学会系期刊可考虑中华医学期刊网读者俱乐部年度会员（含 PDF 下载额度）。\n"]
    groups = {}
    for r, w in miss:
        groups.setdefault(w["venue"] or "（刊名缺失）", []).append(w)
    for venue, ws in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        P.append(f"## {venue}（{len(ws)} 篇）\n")
        for w in ws:
            P.append(f"### {w['year']}《{w['title']}》 {w['volume']}({w['issue']}):{w['pages']}")
            P += purchase_links(w)
            P.append("")
    with open(os.path.join(args.out_dir, "purchase_list.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(P))

    print(f"\n获取 {len(got)}/{total}（{manifest['stats']['success_rate']}%）  分渠道 {by_ch}")
    print(f"清单 -> {args.out_dir}/fulltext_manifest.(json|md)   补取清单 -> {args.out_dir}/purchase_list.md")


if __name__ == "__main__":
    main()
