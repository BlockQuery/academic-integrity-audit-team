<div align="center">

# 学术诚信审计专家团

**Academic Integrity Audit Team** — 一个可复核的学术产出取证工作流

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![WorkBuddy Expert](https://img.shields.io/badge/WorkBuddy-Expert%20Team-7C3AED.svg)](https://www.workbuddy.cn/)
[![Standard Library Only](https://img.shields.io/badge/Dependencies-Stdlib%20Only-green.svg)](#-工具链)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

</div>

> **一句话**：把一位具名学者的公开学术产出，从「名字」查到「可打印的 PDF 报告」——六个角色分工，每一条结论都带证据链、可被引擎反查。
>
> **重要边界**：本项目只产出**线索**，不产出**结论**；只用公开数据，不绕付费墙；不下处分建议。详见 [设计红线](#-设计红线)。

---

## 目录

- [为什么做这个](#-为什么做这个)
- [核心特性](#-核心特性)
- [工作原理](#-工作原理)
- [六维审计](#-六维审计)
- [团队角色](#-团队角色)
- [快速开始](#-快速开始)
- [工具链](#-工具链)
- [目录结构](#-目录结构)
- [输出样例](#-输出样例)
- [设计红线](#-设计红线)
- [常见问题](#-常见问题)
- [贡献](#-贡献)
- [许可证与引用](#-许可证与引用)

---

## 为什么做这个

学术诚信核查的难点不在「查」，在**让结论站得住**：

- 同名学者极多，把别人的论文算到目标头上是最常见、也最致命的错误；
- OpenAlex 的 `funders` 字段只有机构名、**没有批准号**，靠元数据判「基金合规」等于没查；
- 中文非核心刊在英文数据库收录极差，只看英文库必然漏；
- 一份掺了推测的报告，会被对方抓住一处破绽全盘推翻，反过来把委托人拖进名誉侵权。

这个项目把上面这些坑，逐条固化成**机器可跑的脚本 + 人必须守的纪律 + 六角色分工的 SOP**。它不是「一键出结论」的黑箱，而是把「该查什么、查到哪一步能说什么话」写死的审计工作台。

## 核心特性

| 特性 | 说明 |
|---|---|
| **身份先锁定** | 姓名拼音变体穷举 + 机构解析 + ORCID/OpenAlex 锚定，出候选表由人点选，是硬门禁 |
| **中英文双源** | OpenAlex 全量英文题录 + CNKI/RIS/ENW/CSV 中文补检，合并去重 |
| **六维取证** | 身份一致性、产出节奏、专业相关性、期刊质量、学术规范、基金合规、成果一致性 |
| **基金号实战核查** | Europe PMC 取闭源论文批准号 + PDF 全文双源提取，生成待核表，人工去基金委核归属 |
| **四级判语** | A 未发现异常 / B 需说明 / C 高度可疑建议移送 / D 证据不足，禁用「确认造假」等越界表述 |
| **三层标注** | 【事实】【推演】【推测】不混写，每条判断可单独复核 |
| **反向证据义务** | 每个 B 级以上疑点必须写「如果这是正常的会是什么样」 |
| **零第三方依赖** | 全部 Python 脚本仅用标准库，克隆即可跑 |
| **可复现交付** | 报告与全部中间产物同目录，HTML + A4 打印友好 PDF |

## 工作原理

```
Phase 0   立项        主理人收齐四要素 + 三个开关 + 委托用途
   │
Phase 1   身份锁定    甄立言 → 候选表 → 【人工点选·硬门禁】
   │
Phase 2   全网摸底    罗见微 → works_merged.json + 摸底报告 + 盲区声明
   │
Phase 3   双线并行    ┌ 文鉴秋 → 逐篇批注 + 论文审计矩阵
   │                  └ 纪守则 → 项目合规审计 + 基金号待核表
   │
Phase 4   报告汇编    裴成册 → report.md → HTML → PDF
   │
Phase 5   终审        主理人 → 9 项质检清单 → 交付
```

**角色之间不直连**，所有信息流经主理人中转；专业判断只采信对应成员的输出，主理人只做编排与质检。

## 六维审计

| 维度 | 核心问题 | 必查动作 | 自动化上限 |
|---|---|---|---|
| **D0** 身份一致性 | 论文真的都属于本人吗 | 逐篇核孤立论文的作者单位，误并先剔除再重算 | 候选自动，确认人工 |
| **D1** 产出节奏 | 规模与节奏是否可解释 | 年度分布 + 峰值年逐篇核投稿/录用时间 | 全自动 |
| **D2** 专业相关性 | 是否超出本人专业 | 看 topic 主线，跨域论文中本人是否主导 | 信号自动，判断人工 |
| **D3** 期刊质量 | 是否水刊/掠夺性期刊 | 逐刊核收录状态、预警名单、APC、审稿周期 | 信号自动 |
| **D4** 学术规范 | 代写/论文工厂/重复发表 | 图件比对、文本重合、PubPeer、伦理批号 | 仅结构性信号 |
| **D5** 基金合规 | 基金号标注是否真实合规 | 抄录每个基金号 → 基金委平台逐一核验 | 提取自动，归属人工 |
| **D6** 成果一致性 | 履历/结题报告与论文是否对得上 | 申报材料与论文清单比对 | 人工 |

> **D 档不是清白**：任一关键维度（D0/D2/D4/D5）证据不足，综合结论最高只能判 D。没查过的事，不配得到「未发现异常」。

## 团队角色

| 花名 | 头衔 | 职责 | 阶段 |
|---|---|---|---|
| **何秉正** | 首席审计官 | 立项、调度、质检、签字交付 | 全程 |
| **甄立言** | 身份核验专家 | 姓名/单位/领域/职称锁定，出候选让用户点选 | Phase 1 |
| **罗见微** | 公开信息侦察员 | 中英文论文全量清单、项目清单、覆盖盲区声明 | Phase 2 |
| **文鉴秋** | 论文取证审计师 | 水刊、数据造假、专业跨度、单位挂靠、代写信号 | Phase 3A |
| **纪守则** | 科研项目合规审计师 | 基金号真伪、无关内容标注、跨项目重复交账、虚假结题 | Phase 3B |
| **裴成册** | 审计报告主编 | 汇编、统一口径、证据索引、渲染 PDF | Phase 4 |

## 快速开始

### 方式一：作为 WorkBuddy 专家团使用（推荐）

在 WorkBuddy 专家中心导入本项目目录，或上传打包后的 zip，然后在对话中直接说：

> 审计这位学者：姓名、单位、职称我给你。先锁定身份，再摸底全部中英文论文和参与项目，逐篇查水刊、数据造假、基金违规标注，最后出 PDF 报告。

团队会自动按 Phase 0–5 推进，在身份确认处停下来等你点选。

### 方式二：单独跑工具链

```bash
git clone https://github.com/BlockQuery/academic-integrity-audit-team.git
cd academic-integrity-audit-team/skills/academic-misconduct-auditor

# 一键跑通（身份确认处会暂停）
python scripts/run_audit.py --name "San Zhang" --org "示例大学" --field "示例学科" --out case01

# 确认后带 author id 重跑，自动跑完全链路
python scripts/run_audit.py --name "San Zhang" --author-id A0000000000 --out case01 --stamp
```

> 脚本路径相对技能根目录，执行前先 `cd` 过去。实测十余篇论文的完整链路约 70–90 秒，产出 `RUN_SUMMARY.md`（含数据覆盖率与必须人工完成的核查清单）。

### 立项三开关

开工前会确认三项，它们直接决定结论能到哪一档：

| 开关 | 档位 | 影响 |
|---|---|---|
| A 审计深度 | 体检 / 标准 / 深度 | 决定是否逐篇回原文，进而决定结论上限 |
| B 全文获取 | 不下载 / 开放获取全文 | 不开时 D4 只能判 D，不能判 A |
| C 逐篇批注 | 不出 / 批注单 / 批注单 + PDF 批注页 | 决定是否产出逐篇底稿 |

默认推荐：**标准 + 下载全文 + 批注单**；举报用途再加 PDF 批注页。

## 工具链

全部脚本纯 Python 标准库，无 `pip install` 依赖。

| 脚本 | 作用 |
|---|---|
| `fetch_scholar.py` | 身份消歧候选 + 全量题录采集（OpenAlex），带 `risk_flags` 防误并 |
| `import_cnki.py` | 中文题录导入，自动识别 CNKI 文本 / RIS / ENW / CSV |
| `fetch_epmc.py` | Europe PMC 基金批准号与 JATS 全文，闭源论文也能拿号 |
| `fetch_fulltext.py` | 多渠道合法全文获取 + 未获取篇目购买清单，记录来源与许可 |
| `extract_grants.py` | 从 PDF 全文 + EPMC 双源抽取基金号 |
| `analyze_works.py` | 六维指标与规则化信号 |
| `annotate_papers.py` | 逐篇批注单 + PDF 批注页，原始文献字节不动 |
| `render_report.py` | Markdown → 单文件 HTML，A4 打印友好 |
| `render_pdf.py` | Markdown/HTML → PDF，调本机 Edge/Chrome 无头打印 |
| `run_audit.py` | 一键跑通全链路 |

配套参考：`audit_rubric.md`（评分卡与阈值）、`case-playbook.md`（举报实战核查手册）、`fulltext-access.md`（合法全文获取）、`data_sources.md`、`red_lines.md`、`report_spec.md`。

## 目录结构

```
academic-integrity-audit-team/
├── .codebuddy-plugin/
│   └── plugin.json              # 专家团元数据（6 成员、teamInfo、展示字段）
├── agents/                      # 6 个角色定义（1 主理人 + 5 成员）
│   ├── academic-integrity-audit-team-lead.md
│   ├── identity-verifier.md
│   ├── osint-investigator.md
│   ├── paper-forensics.md
│   ├── grant-compliance.md
│   └── report-compiler.md
├── avatars/                     # 统一风格头像（512×512 PNG）
├── skills/academic-misconduct-auditor/
│   ├── SKILL.md                 # 技能主文档（工作流 SOP）
│   ├── scripts/                 # 10 个纯标准库脚本
│   ├── references/              # 评分卡、数据源、红线、报告规范
│   └── assets/                  # 报告模板、期刊预警名单模板
├── tools/
│   └── preflight_expert_pkg.py  # 打包前自检脚本
├── CONTRIBUTING.md
├── CHANGELOG.md
├── SECURITY.md
├── CODE_OF_CONDUCT.md
└── LICENSE
```

## 输出样例

一次完整审计会在案件目录留下可复现的全部产物：

```
audit_<姓名拼音>_<YYYYMMDD>/
├── report.md / report.html / report.pdf   # 主报告与打印版
├── cand.json                              # 身份消歧候选与确认依据
├── works.json / works_merged.json         # 论文全量元数据（含中文补检）
├── metrics_metrics.json / .md             # 六维指标与信号
├── epmc/                                  # Europe PMC 记录与开放全文
├── fulltext/                              # 开放获取全文 + 清单
├── grants/                                # 基金号提取与待核表
└── annotations/                           # 逐篇批注单 + PDF 批注页
```

报告首页给四档综合结论 + 最多 5 条核心疑点 + **至少 1 条「已排除」**；正文每条判断拆【事实】【推演】【推测】，每个 B 级以上疑点配反向证据段，末尾附证据索引与剔除清单。

## 设计红线

这些是写进每个角色的硬约束，违反任一条即终止：

- **不生产结论，只生产线索**：报告用语落在四档，不得写「确认代写」「确认造假」「学术不端成立」。
- **不越公开边界**：只用公开论文/基金库/期刊评价名单/撤稿记录；不查身份证、住址、家庭成员、私人通讯、未公开举报材料。
- **不做人格评价**：只谈文献与数据，不写能力、道德、外貌、性格推测。
- **不绕付费墙**：不用 Sci-Hub 及镜像、不借账号、不伪造鉴权；遇 401/402/403 立即停。证据来路要经得起反查。
- **不下处分建议**：只写「建议移送学术委员会核查」「建议要求提供原始数据」。
- **不编法条**：文件全称、文号、条款号必须核实；核不到就只写文件名与要求内容。
- **原始文献不可改动**：PDF 保持原始字节，批注另存工作副本。
- **原文先于元数据**：基金号、作者位次、期刊信息一律回原文核，元数据只用于发现线索。

> **用途限制**：仅服务本人自查、单位合规审查、实名举报前材料准备、有编辑审核的媒体调查。若委托意图是网络围攻、同行倾轧、商业抹黑，停止并说明原因。

## 常见问题

<details>
<summary>这是「一键出结论」的工具吗？</summary>

不是。身份确认必须人工，基金归属必须人工去官方平台核，判断层必须人写。脚本只做「采集 + 信号提取 + 渲染」，自动化的边界在 SKILL.md 里逐条列明。任何声称「全自动判定学术不端」的用法都违背本项目的设计红线。
</details>

<details>
<summary>为什么 D 档（证据不足）被反复强调？</summary>

因为「没查到」和「没问题」是两回事。没下载全文，就不能判图片复用；没核到基金号，就不能判合规。把数据缺失写成「未发现异常」，是这类审计最严重的失职——报告会被对方一击致命。
</details>

<details>
<summary>中文论文查不全怎么办？</summary>

OpenAlex 对中文非核心刊收录极差。优先用知网/万方导出题录，通过 `import_cnki.py` 导入（覆盖率 90%+）；没有账号时用 WebSearch 检索式 + CSV 整理（30–60%）。浏览器自动化实测不可用。详见 SKILL.md 的 P2.3。
</details>

<details>
<summary>为什么被审计对象本人是通讯作者时不能走「作者索取全文」？</summary>

那等于通知对方你在查他。改走单位图书馆文献传递服务。
</details>

<details>
<summary>报告能直接当举报材料用吗？</summary>

不能直接等同。审计报告是内部底稿，举报材料是对外文书，需按事实链/规则链/责任链重排。`case-playbook.md` 给了完整映射。调查期间不要公开发布——网络曝光会改变案件性质。
</details>

## 贡献

欢迎提 issue 与 PR。尤其是：新的公开数据源接入、中文期刊覆盖改进、判定规则的循证修订、多语言报告模板。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

本项目是一套**方法论工具**，不是法律意见。涉及名誉权、隐私、诉讼策略的，请咨询执业律师。

## 许可证与引用

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) — 自由使用、修改、分发，保留版权声明即可。

如果这个项目帮到了你，欢迎 star ⭐ 或引用：

```bibtex
@misc{academic_integrity_audit_team,
  author = {Zheng, Bo},
  title  = {Academic Integrity Audit Team: A Reproducible Open-Source Workflow for Scholarly Output Forensics},
  year   = {2026},
  url    = {https://github.com/BlockQuery/academic-integrity-audit-team}
}
```

---

<div align="center">

**让每一条结论都经得起逐条反驳。**

</div>
