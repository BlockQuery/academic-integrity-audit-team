#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""专家包上传前预检（模拟平台解析规则）

用法:
  python preflight_expert_pkg.py <包目录>
  python preflight_expert_pkg.py <包目录> --zip        # 预检通过则顺手重新打包

检查项:
  A. plugin.json 可解析、必填字段齐全（对照官方已上架包的最小字段集）
  B. members[] 每人 id / name{en,zh} / profession{en,zh} / avatar / role；与 teamInfo 一致
  C. agents 路径存在，且每个 .md 的 frontmatter name 与文件名一致
  D. teamInfo.memberAgents + agentName 都能在 agents 列表里找到对应文件
  E. avatar / skills 路径存在；skills 目录下有 SKILL.md
  F. 打包洁净度：无 __pycache__ / .DS_Store / 临时文件
  G. 脚本里写死的绝对路径（会上传到别人机器后失效）
"""
import json
import os
import re
import subprocess
import sys
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OK, WARN, FAIL = "  ok  ", " warn ", " FAIL "
errs, warns = [], []


def say(flag, msg):
    print(f"[{flag}] {msg}")
    if flag == FAIL:
        errs.append(msg)
    elif flag == WARN:
        warns.append(msg)


def read(p):
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def frontmatter(text):
    if not text.startswith("---"):
        return {}
    fm = text.split("---", 2)[1]
    d = {}
    for line in fm.splitlines():
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", line)
        if m:
            d[m.group(1)] = m.group(2).strip()
    return d


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    root = os.path.abspath(sys.argv[1])
    do_zip = "--zip" in sys.argv

    pj = os.path.join(root, ".codebuddy-plugin", "plugin.json")
    if not os.path.exists(pj):
        say(FAIL, f"找不到 {pj}")
        finish(root, do_zip)
        return

    try:
        d = json.loads(read(pj))
    except Exception as e:
        say(FAIL, f"plugin.json 不是合法 JSON：{e}")
        finish(root, do_zip)
        return
    say(OK, "plugin.json 可解析")

    # ---- A 必填顶层字段 ----
    need = ["name", "version", "description", "author", "agents", "expertType",
            "agentName", "teamInfo", "displayName", "profession",
            "displayDescription", "avatar", "categoryId", "members"]
    miss = [k for k in need if not d.get(k)]
    say(FAIL if miss else OK, f"顶层必填字段{'缺失: ' + str(miss) if miss else '齐全'}")
    for k in ("displayName", "profession", "displayDescription"):
        v = d.get(k) or {}
        if not (v.get("en") and v.get("zh")):
            say(FAIL, f"{k} 需要 en/zh 双语")
    if not (d.get("defaultInitPrompt") or {}).get("zh"):
        say(WARN, "defaultInitPrompt 缺 zh，平台可能显示为空")

    # ---- B members ----
    agents_rel = [os.path.normpath(a) for a in (d.get("agents") or [])]
    agent_names = {}
    for rel in agents_rel:
        p = os.path.join(root, rel)
        if not os.path.exists(p):
            say(FAIL, f"agents 里登记的 {rel} 不存在")
            continue
        fm = frontmatter(read(p))
        nm = fm.get("name") or ""
        agent_names[nm] = rel
        stem = os.path.splitext(os.path.basename(rel))[0]
        if nm != stem:
            say(WARN, f"{rel} 的 frontmatter name='{nm}' 与文件名不一致")
        if not fm.get("description"):
            say(WARN, f"{rel} 缺 description")

    ids = []
    for i, m in enumerate(d.get("members") or []):
        mid = m.get("id") or f"members[{i}]"
        ids.append(m.get("id"))
        for f in ("name", "profession"):
            v = m.get(f)
            if not isinstance(v, dict) or not (v.get("en") and v.get("zh")):
                say(FAIL, f"members[{i}].{f} 的 en/zh 均为必填（{mid}）")
        for f in ("id", "avatar", "role"):
            if not m.get(f):
                say(FAIL, f"members[{i}].{f} 缺失（{mid}）")
        av = m.get("avatar")
        if av and not os.path.exists(os.path.join(root, av)):
            say(FAIL, f"members[{i}] 头像不存在：{av}")
        if m.get("role") not in ("lead", "member"):
            say(WARN, f"members[{i}].role='{m.get('role')}' 非常见值（lead/member）")

    # ---- C/D 交叉引用 ----
    ti = d.get("teamInfo") or {}
    lead, mems = ti.get("leadAgent"), ti.get("memberAgents") or []
    if d.get("agentName") != lead:
        say(FAIL, f"agentName({d.get('agentName')}) 与 teamInfo.leadAgent({lead}) 不一致")
    for a in [lead] + list(mems):
        if a not in agent_names:
            say(FAIL, f"teamInfo 引用的 '{a}' 在 agents 里找不到对应的 .md name")
    if set(ids) - {None} != {lead} | set(mems):
        say(WARN, f"members 的 id 集合与 teamInfo 不完全对应：members={ids} teamInfo={[lead]+list(mems)}")
    if not errs:
        say(OK, f"成员/agent 交叉引用闭合（{len(ids)} 人，lead={lead}）")

    # ---- E skills / avatar ----
    av = d.get("avatar")
    if av and not os.path.exists(os.path.join(root, av)):
        say(FAIL, f"团队头像不存在：{av}")
    for s in d.get("skills") or []:
        sp = os.path.join(root, os.path.normpath(s))
        if not os.path.isdir(sp):
            say(FAIL, f"skills 登记的 {s} 不是目录")
        elif not os.path.exists(os.path.join(sp, "SKILL.md")):
            say(FAIL, f"{s} 下没有 SKILL.md")

    # ---- F 洁净度 ----
    junk = []
    for dp, dn, fn in os.walk(root):
        for x in list(dn):
            if x in ("__pycache__", ".git", "node_modules"):
                junk.append(os.path.join(dp, x))
        for x in fn:
            if x in (".DS_Store", "Thumbs.db") or x.endswith((".pyc", ".zip", ".tmp", ".bak")):
                junk.append(os.path.join(dp, x))
    say(WARN if junk else OK,
        f"待清理文件 {len(junk)} 个" + (f"（{'; '.join(os.path.relpath(j, root) for j in junk[:5])}）" if junk else "，干净"))

    # ---- G 绝对路径 ----
    hard = []
    for dp, dn, fn in os.walk(root):
        for x in fn:
            if not x.endswith((".py", ".md", ".json", ".sh")):
                continue
            p = os.path.join(dp, x)
            try:
                t = read(p)
            except Exception:
                continue
            for m in re.finditer(r"[A-Za-z]:[\\/](?:Users|workbuddy|Program)[\\/][^\s\"'）)]*", t):
                hard.append(f"{os.path.relpath(p, root)}: {m.group(0)[:60]}")
    say(WARN if hard else OK,
        f"写死的本机绝对路径 {len(hard)} 处" + (f"：{hard[0]}" if hard else "，无"))

    finish(root, do_zip)


def finish(root, do_zip):
    print()
    if errs:
        print(f"结论：{len(errs)} 项阻断，{len(warns)} 项提醒 —— 不能上传")
        sys.exit(1)
    print(f"结论：0 项阻断，{len(warns)} 项提醒 —— 可以上传")
    if do_zip:
        name = os.path.basename(root.rstrip("/\\"))
        out = os.path.join(os.path.dirname(root), name + ".zip")
        if os.path.exists(out):
            os.remove(out)
        n = 0
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for dp, dn, fn in os.walk(root):
                dn[:] = [x for x in dn if x not in ("__pycache__", ".git", "node_modules")]
                for x in sorted(fn):
                    if x in (".DS_Store", "Thumbs.db") or x.endswith((".pyc", ".zip", ".tmp", ".bak")):
                        continue
                    p = os.path.join(dp, x)
                    z.write(p, os.path.join(name, os.path.relpath(p, root)))
                    n += 1
        print(f"已打包 {n} 个文件 -> {out}（{os.path.getsize(out)/1024/1024:.2f} MB）")


if __name__ == "__main__":
    main()
