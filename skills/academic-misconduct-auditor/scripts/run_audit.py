#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键编排：从姓名到审计底稿

用法:
  # 第一步（必须）：先看候选，人工确认
  python run_audit.py --name "San Zhang" --org "示例大学" --field "示例学科" --out case01

  # 第二步：确认后带 author-id 重跑
  python run_audit.py --name "San Zhang" --author-id A0000000000 --out case01

  # 选项
  --depth check|standard|deep   审计深度（默认 standard）
  --no-fulltext                 不下载全文（快，但 D4 只能判 D）
  --stamp                       在 PDF 前插审计批注页（慢）
  --watchlist wl.csv            期刊预警名单

设计原则:
  1. **身份确认是硬门禁**：没有 --author-id 或 --yes，脚本在候选列表处停下退出。
     全自动选人必然产生误判，误判的代价是查错人，这是不可接受的风险。
  2. **不伪造完成度**：跑完不等于查完。输出里显式列出"必须人工完成的核查项"。
  3. **不绕付费墙**：全文只取开放获取（OpenAlex + PMC 开放子集）。
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def run(script, args, label, critical=True):
    """执行一个子脚本，返回 (成功?, 输出文本)。"""
    cmd = [PY, os.path.join(HERE, script)] + args
    print(f"\n{'='*68}\n▶ {label}\n{'='*68}")
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (p.stdout or "") + (p.stderr or "")
    print(out.strip()[-1600:] if out.strip() else "（无输出）")
    ok = p.returncode == 0
    print(f"— {label} {'完成' if ok else '失败'}（{time.time()-t0:.1f}s）")
    if not ok and critical:
        print(f"\n✗ 关键步骤失败，流程中止：{label}")
        sys.exit(1)
    return ok, out


def main():
    ap = argparse.ArgumentParser(description="学术审计一键编排")
    ap.add_argument("--name", required=True)
    ap.add_argument("--org")
    ap.add_argument("--field")
    ap.add_argument("--gender", help="仅记录到报告，不参与检索")
    ap.add_argument("--author-id")
    ap.add_argument("--yes", action="store_true", help="自动采用首选候选（不推荐，仅在已确认时使用）")
    ap.add_argument("--out", default="audit_case")
    ap.add_argument("--depth", choices=["check", "standard", "deep"], default="standard")
    ap.add_argument("--no-fulltext", action="store_true")
    ap.add_argument("--stamp", action="store_true")
    ap.add_argument("--watchlist")
    ap.add_argument("--cnki", help="知网/万方/RIS/EndNote 导出的题录文件，合并进成果清单")
    ap.add_argument("--alias", help="其他姓名写法，逗号分隔（中文题录需给中文名），如 张三")
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    started = datetime.now()

    base = ["--name", args.name]
    if args.org:
        base += ["--org", args.org]
    if args.field:
        base += ["--field", args.field]

    # ---------- 阶段 1：身份消歧（硬门禁） ----------
    if not args.author_id:
        run("fetch_scholar.py", ["candidates"] + base + ["--out", os.path.join(out, "cand.json")],
            "阶段 1/7 身份消歧")
        if not args.yes:
            print("\n" + "!" * 68)
            print("已停在身份确认处。这是设计的一部分，不是故障。")
            print("同名学者会导致整份审计查错人，必须由你确认是哪一位。")
            print("\n确认后重跑：")
            print(f'  python run_audit.py --name "{args.name}" --author-id <选中的ID> --out {args.out}')
            print("\n（若已确认首选候选无误，加 --yes 跳过本提示）")
            print("!" * 68)
            sys.exit(2)
        with open(os.path.join(out, "cand.json"), encoding="utf-8") as f:
            cand = json.load(f)
        rows = cand.get("candidates") or []
        if not rows:
            print("✗ 未检索到候选，请补单位或用拼音重试。")
            sys.exit(1)
        args.author_id = rows[0]["openalex_id"]
        print(f"\n[--yes] 采用首选候选：{rows[0]['name']}（{args.author_id}）")

    # ---------- 阶段 2：论文元数据 ----------
    works_path = os.path.join(out, "works.json")
    run("fetch_scholar.py", ["works", "--author-id", args.author_id, "--out", works_path],
        "阶段 2/7 全量论文采集")

    # ---------- 阶段 2b：中文题录导入（可选） ----------
    if args.cnki:
        merged = os.path.join(out, "works_merged.json")
        run("import_cnki.py", ["--input", args.cnki, "--works", works_path,
                               "--name", args.name, "--out", merged,
                               "--report", os.path.join(out, "cnki_import_report.md")]
            + (["--alias", args.alias] if args.alias else [])
            + (["--default-field", args.field] if args.field else []),
            "阶段 2b 中文题录导入", critical=False)
        if os.path.exists(merged):
            works_path = merged

    # ---------- 阶段 3：Europe PMC（基金 + 开放全文） ----------
    epmc_dir = os.path.join(out, "epmc")
    run("fetch_epmc.py", ["--works", works_path, "--out", epmc_dir],
        "阶段 3/7 Europe PMC（含付费墙论文的基金批准号）", critical=False)

    # ---------- 阶段 4：全文与基金提取（必须先于指标分析，否则用不到批准号） ----------
    ft_dir = os.path.join(out, "fulltext")
    grants_dir = os.path.join(out, "grants")
    if not args.no_fulltext:
        run("fetch_fulltext.py", ["--input", works_path, "--out-dir", ft_dir],
            "阶段 4/7 开放获取全文", critical=False)
        run("extract_grants.py", ["--works", works_path, "--fulltext", ft_dir,
                                  "--out", grants_dir],
            "阶段 4b 基金号提取（PDF 原文）", critical=False)
    else:
        print("\n[跳过] 全文下载（--no-fulltext）：D4 将判为证据不足")

    # ---------- 阶段 5：指标与信号（按批准号聚合，需 grants 先行） ----------
    analyze_args = ["--input", works_path, "--out-prefix", os.path.join(out, "metrics")]
    if args.watchlist:
        analyze_args += ["--watchlist", args.watchlist]
    gp = os.path.join(grants_dir, "grants_extracted.json")
    if os.path.exists(gp):
        analyze_args += ["--grants", gp]
    if os.path.isdir(epmc_dir):
        analyze_args += ["--epmc", epmc_dir]
    run("analyze_works.py", analyze_args, "阶段 5/7 指标计算与规则信号")

    # ---------- 阶段 6：逐篇批注 ----------
    ann_args = ["--works", works_path, "--metrics", os.path.join(out, "metrics_metrics.json"),
                "--fulltext", ft_dir, "--epmc", epmc_dir, "--out", os.path.join(out, "annotations")]
    if args.stamp and not args.no_fulltext:
        ann_args.append("--stamp")
    run("annotate_papers.py", ann_args, "阶段 6/7 逐篇审计批注", critical=False)

    # ---------- 阶段 7：汇总与待办 ----------
    print(f"\n{'='*68}\n▶ 阶段 7/7 汇总\n{'='*68}")
    metrics = {}
    mp = os.path.join(out, "metrics_metrics.json")
    if os.path.exists(mp):
        with open(mp, encoding="utf-8") as f:
            metrics = json.load(f)
    manifest = {}
    fmp = os.path.join(ft_dir, "fulltext_manifest.json")
    if os.path.exists(fmp):
        with open(fmp, encoding="utf-8") as f:
            manifest = json.load(f)
    epmc = {}
    ep = os.path.join(epmc_dir, "epmc_records.json")
    if os.path.exists(ep):
        with open(ep, encoding="utf-8") as f:
            epmc = json.load(f)

    summ = metrics.get("summary") or {}
    fs = (manifest.get("stats") or {})
    es = (epmc.get("stats") or {})
    n_total = summ.get("total_works") or 0
    n_pdf = fs.get("obtained") or 0
    n_pmc = es.get("with_fulltext") or 0

    # 按 DOI 取并集，PDF 与 PMC 常有重叠
    pdf_dois = {(i.get("doi") or i.get("id")) for i in (manifest.get("items") or []) if i.get("file")}
    xml_dois = {(i.get("doi") or i.get("id")) for i in (epmc.get("items") or []) if i.get("fulltext_file")}
    readable_dois = pdf_dois | xml_dois
    n_readable = len(readable_dois)

    signals = metrics.get("signals") or []
    high = [s for s in signals if s.get("severity") == "high"]
    ann_dir = os.path.join(out, "annotations")
    n_ann = len([f for f in os.listdir(ann_dir) if f.endswith(".md") and f != "index.md"]) if os.path.isdir(ann_dir) else 0

    lines = [
        f"# 审计运行汇总：{args.name}",
        "",
        f"- 运行时间：{started.strftime('%Y-%m-%d %H:%M')}　耗时 {(datetime.now()-started).seconds} 秒",
        f"- 审计深度：{args.depth}　OpenAlex ID：{args.author_id}",
        f"- 单位：{args.org or '—'}　领域：{args.field or '—'}　性别：{args.gender or '未提供'}",
        "",
        "## 数据获取情况",
        "",
        "| 项 | 数量 | 说明 |",
        "|---|---|---|",
        f"| 论文总数 | {n_total} | OpenAlex 收录量，不等于本人全部成果 |",
        f"| 全文可读 | {n_readable} | PDF {n_pdf} 篇、PMC XML {n_pmc} 篇，按 DOI 去重后 {n_readable} 篇 |",
        f"| 基金批准号 | {(es.get('with_grants') or 0)} 篇 | 来自 Europe PMC，含付费墙论文 |",
        f"| 逐篇批注 | {n_ann} 份 | |",
        "",
        f"**全文覆盖率 {round(n_readable*100.0/n_total,1) if n_total else 0}%**。未覆盖的篇目，依赖全文的维度（图片复用、伦理批号、样本量）判为证据不足。",
        "",
        "## 自动检出的信号",
        "",
    ]
    if signals:
        lines += ["| 编号 | 维度 | 信号 | 严重度 |", "|---|---|---|---|"]
        for s in signals:
            lines.append(f"| {s['id']} | {s['dimension']} | {s['title'][:70]} | {s['severity']} |")
    else:
        lines.append("未触发规则信号。**规则未触发不等于无问题**，仅表示元数据层面无异常。")
    lines += ["", "## 必须人工完成的核查（工具做不到的部分）", ""]

    todo = []
    if high:
        todo.append(f"**高严重度信号 {len(high)} 条**，必须逐条回原文核实，不得直接写入结论。")
    if n_readable < n_total:
        todo.append(f"**{n_total-n_readable} 篇无可读全文**。需通过单位图书馆文献传递或联系通讯作者获取；"
                    f"在拿到之前，这些篇目的 D4 只能判「证据不足」。")
    todo.append("**基金批准号归属核验**：拿提取到的号码逐一去 kd.nsfc.cn 查负责人、依托单位、"
                "执行期、研究内容。该站为 JS 应用，脚本抓不到，必须人工查。")
    todo.append("**图片复用比对**：需人眼逐篇比对同作者的 Western blot / 显微图 / 流式图。"
                "自动化工具（ImageTwin、Proofig）需付费，且最终判断仍要人做。")
    todo.append("**中文期刊补检**：OpenAlex 对中文刊覆盖差，需用知网/万方按「作者+单位」补检，"
                "结果手工并入 works.json。")
    todo.append("**身份误并复核**：检查 identity_check 中的孤立论文，确认其署名单位是否为目标单位；"
                "误并的必须剔除后重算指标。")
    todo.append("**代写与数据造假定性**：公开数据无法证明，只能输出「与代写模式一致的特征」，"
                "不得下确定性结论。")

    for i, t in enumerate(todo, 1):
        lines.append(f"{i}. {t}")
    lines += [
        "",
        "## 产出文件",
        "",
        "| 文件 | 内容 |",
        "|---|---|",
        "| `cand.json` | 身份消歧候选与确认依据 |",
        "| `works.json` | 论文全量元数据 |",
        "| `metrics_metrics.md` | 指标摘要与信号清单 |",
        "| `epmc/epmc_summary.md` | Europe PMC 采集结果（含付费墙论文基金号） |",
        "| `fulltext/` | 开放获取 PDF |",
        "| `grants/grants_extracted.md` | 基金标注提取与待核表 |",
        "| `annotations/` | 逐篇审计批注单 + PDF 批注页 |",
        "",
        "## 下一步",
        "",
        "1. 打开 `annotations/index.md`，按篇核对",
        f"2. 完成上面 {len(todo)} 项人工核查",
        "3. 按 `assets/report_template.md` 撰写报告，或让审计专家基于本目录生成",
    ]
    sp = os.path.join(out, "RUN_SUMMARY.md")
    with open(sp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"论文 {n_total} 篇｜可读全文 {n_readable} 篇（{round(n_readable*100.0/n_total,1) if n_total else 0}%）"
          f"｜信号 {len(signals)} 条（高严重度 {len(high)}）")
    print(f"\n汇总 -> {sp}")
    print("\n提示：这不是一份完成的审计。上面列出的 %d 项人工核查做完，才谈得上结论。" % len(todo))


if __name__ == "__main__":
    main()
