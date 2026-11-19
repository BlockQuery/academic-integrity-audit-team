---
name: academic-misconduct-auditor
display_name: 学术不端检测器
display_name_en: Academic Misconduct Auditor
description: 学术不端检测器。输入人物姓名、工作单位、性别或所在领域，先做身份消歧并由用户确认目标，再检索其全网公开论文，逐篇审核专业相关性、期刊质量（水刊/掠夺性期刊）、代写与论文工厂信号、基金标注合规性（含国家自然科学基金）、撤稿与重复发表，输出带完整证据链和分级结论的调查分析报告。当用户要求核查某位学者论文是否造假/灌水/代写、基金标注是否合规、成果与履历是否对得上，或需要整理实名举报、职称评审、单位合规审查的材料时使用。
description_zh: 消歧锁定学者，检索全网论文，六维核查专业跨度、水刊、代写信号与国自然合规，输出带证据链的审计报告。
description_en: Disambiguate a named scholar, harvest all public papers, and audit specialty drift, predatory journals, ghostwriting signals, retraction and NSFC grant compliance into an evidence-chained report.
version: 1.6.0
author: 郑博
category: 效率工具
agent_created: true
---

# 学术不端检测器

对一个具名学者做基于**公开学术元数据与公开文献**的结构化审计，产出可核查、可复现、可被第三方复核的线索清单与调查分析报告。

## 一、这个技能不做什么

先划边界，违反任一条即终止任务：

- **不生产结论，只生产线索。** 公开数据能证明"某篇论文存在"，不能证明"某人主观造假"。报告用语必须落在"未发现异常 / 需说明的疑点 / 高度可疑 / 证据不足"四档，不得写"确认代写""确认造假"。
- **不越公开边界。** 只使用公开发表的论文、公开的基金项目库、公开的期刊评价名单、公开的撤稿记录。不查身份证、住址、家庭成员、私人通讯、未公开的举报材料。
- **不做人格评价。** 不写能力评价、道德判断、外貌、性格、人际关系推测。报告只谈文献与数据。
- **用途受限。** 仅服务：本人自查、所在单位合规审查、实名举报前的材料准备、有编辑审核的媒体调查。若委托意图是网络围攻、同行倾轧、商业竞争抹黑，停止并说明原因。

## 二、铁律

1. **身份消歧必须前置并留痕。** 同名学者极多，把所有论文算到目标头上是最常见也最致命的错误。未经用户确认候选身份，不得进入审核阶段。确认记录写进报告（候选人 ID、依据、确认方式）。
2. **三层标注。** 每条判断标注【事实】（可直接指认原文/数据库记录）、【推演】（由事实按明确逻辑导出）、【推测】（需进一步取证）。三者不得混写在同一句里。
3. **反向证据义务。** 每个疑点必须同时列出"支持正常解释的证据"。只找罪证的报告在复核环节会整体失效，也会让委托人承担名誉侵权风险。
4. **口径先声明，再计算。** 报告开头写明：数据源、检索日期、检索式、覆盖盲区、排除项（如被判定为误并的论文）。没有口径声明的统计数字不可用。
5. **不替委托人下处分建议。** 可以写"建议移送学术委员会核查""建议要求提供原始数据"，不写"应撤销职称""应开除"。
6. **每条证据带来源与时间戳。** DOI、数据库记录号、网页 URL + 访问日期。无来源的判断一律删除。
7. **原始文献不可改动。** 下载的 PDF 保持原始字节，批注另存工作副本（`*_annotated.pdf`）。任何时候都要能出示未经修改的原文——这是证据完整性的底线，也是被反查时的唯一自保。
8. **D 档不是结论，是未完成。** 任一关键维度（D0/D2/D4/D5）判 D，综合结论**最高只能是「证据不足」**。该维度内禁止出现"未发现""不构成""未见异常"等正面表述——没查过的事，不配得到清白。这是这类审计最严重的错误类型：把数据缺失写成没问题。详见 `references/audit_rubric.md` 的三条强制降级规则。

## 三、工作流

### 速查：一键入口（推荐）

```bash
# 第一条命令会停在候选确认处，这是设计的一部分
python scripts/run_audit.py --name "San Zhang" --org "示例大学" --field "示例学科" --out case01

# 确认身份后带 author id 重跑，自动跑完 7 个阶段
python scripts/run_audit.py --name "San Zhang" --author-id A0000000000 --out case01 --stamp
```

实测：13 篇论文的完整链路约 70–90 秒跑完，产出 `RUN_SUMMARY.md`（含数据覆盖率和必须人工完成的核查清单）。

**"一键"的边界**（必须向用户讲清，否则就是过度承诺）：

| 环节 | 自动化 | 说明 |
|---|---|---|
| 身份消歧 | 候选自动，**确认必须人工** | 全自动选人必然产生误判，查错人的代价不可接受 |
| 题录采集 | 全自动 | 但 OpenAlex 收录量 ≠ 本人全部成果 |
| 全文获取 | 部分自动 | 开放获取约 30–60%，其余在付费墙后 |
| 指标与信号 | 全自动 | 信号不是结论 |
| 基金号提取 | 全自动 | 归属核验必须人工去 kd.nsfc.cn |
| 图片复用/代写 | **不能自动定性** | 只能给结构性信号 |
| 报告撰写 | 半自动 | 事实层自动，判断层必须人写 |

### 速查：分步执行（需要精细控制时）

```bash
CASE="audit_<拼音>_$(date +%Y%m%d)"; mkdir -p "$CASE"

# 1 消歧（机构名可直接传中文，脚本会解析成 OpenAlex 机构记录）
python scripts/fetch_scholar.py candidates --name "San Zhang" --org "示例大学" --field "示例学科" --out "$CASE/cand.json"
#    → 到此暂停，向用户确认身份

# 2 采集（用确认后的 author id 或 ORCID）
python scripts/fetch_scholar.py works --author-id A0000000000 --out "$CASE/works.json"

# 3 指标（watchlist.csv 可选，格式见 assets/watchlist_template.csv）
python scripts/analyze_works.py --input "$CASE/works.json" --watchlist "$CASE/watchlist.csv" --out-prefix "$CASE/metrics"

# 3.4 中文题录导入（导出文件或 WebSearch 整理的 CSV；见 P2.3）
python scripts/import_cnki.py --input 题录.csv --works "$CASE/works.json" --name "<拼音名>" --alias "<中文名>" --out "$CASE/works_merged.json"

# 3.5 全文（可选，见 P0 选项 B；只取开放获取，不绕付费墙）
python scripts/fetch_fulltext.py --input "$CASE/works.json" --out-dir "$CASE/fulltext"

# 3.6 Europe PMC（强烈建议：付费墙论文也能拿到基金批准号 + PMC 开放全文）
python scripts/fetch_epmc.py --works "$CASE/works.json" --out "$CASE/epmc"

# 3.7 基金号提取（PDF 全文 + EPMC 双源）
python scripts/extract_grants.py --works "$CASE/works.json" --fulltext "$CASE/fulltext" --out "$CASE/grants"

# 3.8 逐篇批注（可选，见 P0 选项 C）
python scripts/annotate_papers.py --works "$CASE/works.json" --metrics "$CASE/metrics_metrics.json" \
    --fulltext "$CASE/fulltext" --epmc "$CASE/epmc" --out "$CASE/annotations" --stamp

# 4 渲染
python scripts/render_report.py --input "$CASE/report.md" --output "$CASE/report.html" --title "学术成果审计报告：<姓名>"

# 5 出 PDF（委托方通常只认 PDF）
python scripts/render_pdf.py --input "$CASE/report.md" --output "$CASE/report.pdf"
```

脚本路径相对于技能根目录，执行前 `cd` 到技能目录或使用绝对路径。PowerShell 环境下改用 `New-Item -ItemType Directory`、`Get-Date -Format yyyyMMdd` 与 `$CASE` 变量。

确认候选时用 `AskUserQuestion` 呈现 2–4 个高相关候选，label 写成 `姓名｜单位｜论文量`，让用户点选，不要让用户手打 ID。

### P0 立项（受理）

收集四要素：姓名、工作单位、性别、领域。缺项按下列规则处理：

| 缺失 | 处理 |
|---|---|
| 单位 | 必须追问。无单位时同名候选可达数十人，无法消歧 |
| 性别 | 可选。仅在候选姓名跨性别时用于排除（如 "Jian Zhang"） |
| 领域 | 可选但强烈建议。用于候选排序与 D2 判定基准 |
| 姓名非中文 | 直接用原拼写检索；中文姓名须先转拼音并准备 2–3 种写法（如 张三 → San Zhang / Zhang San / Zhang San） |

同时确认委托用途（自查/单位审查/举报准备/媒体调查），记入报告首页。用途不合规则终止。

**必须确认三项选项**，它们决定工作量、交付物形态和结论能到哪一档：

| 选项 | 档位 | 影响 |
|---|---|---|
| **A 审计深度** | 体检 / 标准 / 深度 | 决定是否逐篇回原文，进而决定结论上限 |
| **B 全文获取** | 不下载 / 下载开放获取全文 | 决定 D4（图片复用、伦理批号、样本量）能否核查 |
| **C 逐篇批注** | 不出 / 批注单 / 批注单 + PDF 批注页 | 决定是否产出逐篇底稿 |

**A 深度分档**

| 档 | 工作量 | 做什么 | 结论上限 |
|---|---|---|---|
| 体检 | 分钟级 | 只跑脚本，出指标与信号，不回原文 | 最高 B。D4 基本只能是 D |
| 标准 | 小时级 | 核心疑点回原文核对，D5 逐篇抄基金号去基金委核 | 可达 C |
| 深度 | 天级 | 全篇下载、逐篇图件比对、伦理批号与注册号核验、APC 线索 | 可达 C |

**B 的前置约束必须向用户讲清**：不下载全文时，D4 的图片复用、伦理批号、样本量一致性**无法核查**。此时该维只能判 D（证据不足），**不得判 A（未发现异常）**。这两句话意思完全不同，混淆会让委托方误以为"查过了没问题"。

**C 的输出形态**

- 批注单：每篇一份 Markdown，含事实字段、待核清单、审计判断表（判断留空由审计人填）
- PDF 批注页：在每篇 PDF 前插入一页 A4 批注页（复选框 + 结论栏），原文件不动，另存为 `_annotated.pdf` 工作副本。适合打印出来手写批注或作为举报附件

默认建议：**标准 + 下载全文 + 批注单**。举报用途建议再开 PDF 批注页。

### P1 身份消歧（硬门禁）

```bash
python scripts/fetch_scholar.py candidates --name "San Zhang" --org "示例大学" --field "示例学科" --out cand.json
```

脚本会先把中文机构名解析为 OpenAlex 机构记录（拿到标准英文名与机构 ID），再用「姓名 + 机构」组合过滤，输出带 `match_score`、`match_reason` 与 **`risk_flags`** 的候选表。

**`risk_flags` 比分数重要**，三种标记各有含义：

| 标记 | 含义 | 处理 |
|---|---|---|
| `merged_suspect` | 档案含 ≥2 个非目标机构，极可能是多个同名者被并成一条记录 | **禁止按该 ID 全量取数**，逐篇核单位与通讯邮箱 |
| `co_affiliation_or_merge` | 含 1 个非目标机构 | 可能是兼职/就读/合作，也可能是并档，逐篇核 |
| `fragment_suspect` | 机构一致但论文量极少 | 可能是同一自然人的碎片档案，按通讯邮箱或长期合作者归并去重 |

实战教训：某次消歧里，OpenAlex 把「示例大学示例学科 + 另一医科大学检验 + 某中心医院肿瘤科」三个同名者并进一条 13 篇的档案，原始打分把它排第一；同时该学者本人的 2 篇、1 篇成果被拆成两条碎片档案排在最后。**按分数选人，会同时多收别人的论文、漏收他本人的论文。** 分数只用于排序，选人靠逐条排除。

把候选表**原样呈现给用户**，逐条列出：姓名写法、署名单位、论文量、h 指数、主要研究主题、ORCID。然后要求用户确认，或提供更精确的标识（ORCID 优先）。

补充检索手段（脚本覆盖不到时用）：
- WebSearch：`"姓名" "单位" ORCID`、`"姓名" 学者主页`、`researchgate.net/profile/`、`scholar.google.com`
- 中文库：知网作者库、万方学者库、百度学术。中文库对中文姓名支持好，是消歧的重要交叉源
- 单位官网师资页：通常有职称、研究方向、代表作列表，是"官方口径"

确认后记录 `openalex_id` 或 `orcid`，写入报告的"审计对象"节。

**门禁规则**：候选 ≥2 位且用户未明确选择时，禁止继续。不得用"最高分即本人"代替确认，除非用户明确授权（此时报告中注明"未获人工确认，按算法首选执行"）。

### P2 论文全量采集

```bash
python scripts/fetch_scholar.py works --author-id A0000000000 --out works.json
```

采集字段：标题、DOI、年份、期刊/出版社、ISSN、OA 状态、被引、作者位次与是否通讯、合作者、基金资助方、OpenAlex 主题层级（topic/subfield/field/domain）、撤稿标记、语言。

**必须补检的三类内容**（OpenAlex 覆盖不足，不补检就会漏）：

1. **中文期刊论文**：OpenAlex 对中文非核心刊收录很差。用知网/万方按作者+单位检索，把结果手工并入清单，标注"来源：CNKI 补检"。
2. **撤稿与质疑**：Retraction Watch 数据库、期刊官网撤稿声明、PubPeer 条目。
3. **非论文成果**：专利、标准、学位论文、会议摘要。若委托涉及职称或结题，这些会影响"成果规模"判断。

采集完成后统计去重：同一论文在不同库重复、中英文双版（中文刊 + 英文刊同内容）要合并或标注，否则会虚增产出量。

### P2.3 中文成果补检（必做）

**为什么必做**：OpenAlex 对中文期刊（尤其非核心刊、校内学报）收录极差。实测某学院院长，英文库仅 1 篇，而中文至少有 3 篇发在校内学报——不补检，报告就是残缺的。

**三条路径，按可行性排序**

| 路径 | 覆盖率 | 需要条件 | 备注 |
|---|---|---|---|
| **A. 导出题录导入** | 90%+ | 知网/万方账号 | 一次可导 50–500 条，最完整 |
| **B. WebSearch 检索 + CSV 整理** | 30–60% | 无 | agent 可自动执行，见下 |
| C. 浏览器自动化 | 0 | — | **实测不可用**：知网 `ERR_CERT_COMMON_NAME_INVALID`，万方跳人机验证页 |

**先试 A，没有账号就用 B。**

**路径 B 的操作法**：用 WebSearch 按下列检索式搜索，从返回的知网/万方/NSTL 页面里抄出题录，整理成 CSV：

```
"<姓名>" <单位关键词> 论文
"<姓名>" 知网 期刊
"<姓名>" <研究方向关键词> 示例大学学报
```

搜索结果的摘要里通常就带完整的参考文献格式（作者、篇名、刊名、年卷期页、DOI、基金），照抄即可。

**CSV 格式**（字段名支持中英文）：

```csv
title,authors,venue,year,volume,issue,pages,doi,fund,keywords
某示例论文标题,示例作者甲;示例作者乙;示例作者丙,示例大学学报(自然科学版),2022,38,11,12-16,10.00000/example.2022.11.001,某省高等学校科学研究项目(EX2022001),示例方向甲;示例方向乙
```

```bash
python scripts/import_cnki.py --input 题录.csv --works works.json --name "Mou Shili" --alias "示例作者甲" --out works_merged.json --default-field "示例学科"
```

`import_cnki.py` 支持 **CNKI 文本导出 / RIS / EndNote ENW / CSV** 四种格式，自动识别。

**三个必须核对的点**：

| 项 | 为什么 |
|---|---|
| **作者位次** | 位次错会扭曲"是否主导"。脚本按姓名精确/包含两轮匹配，报告标注匹配方式 |
| **未匹配清单** | 作者列表里找不到本人的题录，可能是同名他人。**未确认前不得计入成果** |
| **Fund 字段** | 知网常只写基金名称不写批准号，需回原文补 |

**注意**：中文题录录入后，`analyze_works.py` 的 S0（作者档案误并）判定会自动排除 `source=cnki-import` 的条目——中英文论文的合作者天然是两套人，跨源比较必然假阳性。

导入后续流程全部改用 `works_merged.json`。

### P2.5 全文获取（选项 B 开启时）

```bash
UNPAYWALL_EMAIL=<单位邮箱> python scripts/fetch_fulltext.py --input works.json --out-dir fulltext
# 输入也可以是 CSV（title,venue,year,doi 列），如中文题录 works_cn.csv
```

**多渠道阶梯（逐篇逐渠道，拿到即停）**：OpenAlex 全部 locations（无 DOI 按标题严格匹配检索）→ Unpaywall（需设 `UNPAYWALL_EMAIL`，未设置自动跳过，绝不使用默认邮箱）→ Semantic Scholar openAccessPdf → Europe PMC（`inPMC=Y` 取 JATS XML，并回收 grantsList）→ arXiv → `references/journal_sites.json` 登记的期刊官网免费 PDF → 兜底生成 `purchase_list.md`。

- **不绕过付费墙**：遇 401/402/403 立即停该渠道，不重试、不换 UA；不使用 Sci-Hub 及镜像、不伪造鉴权、不借账号
- 校验 `%PDF-` 魔数与体积，防止把 HTML 落地页当成 PDF 存下来
- 每份文件记录 `source_channel` / `url` / `license` / `sha256` / `fetched_at`；报告据此标注来源
- 产物：`fulltext_manifest.json|md`（含分渠道获取率）、`purchase_list.md`（未获取篇目按刊分组，附 DOI/知网/万方/NSTL 入口）
- `level=abstract` 的文件（如期刊官网摘要 PDF）**不得当全文使用**，对应维度仍判 D

现实预期：英文生物医学刊 60–80% 可得；**中文刊、2010 年前老论文通常接近 0**（实测某测试案例案 25 篇中文为主：0/25）。这时 purchase_list 才是主产出——把"拿不到"变成"买哪几篇、去哪买"。给 purchase_list 排优先级时，只买**支撑结论的关键篇**（疑似图片复用/数据矛盾/基金标注核查对象）。

**journal_sites.json 维护**：发现某刊官网公开提供免费 PDF（先在浏览器确认无需登录），按文件内模板追加登记（`match` 刊名关键词 + `detail_url_template` + `direct_pdf_regex_page`），之后所有案件自动受益。

**严禁绕过付费墙**：不用 Sci-Hub、不借账号、不伪造鉴权、不爬付费页面。原因很实际——报告常用于举报与评审，证据来路不正会被对方一击致命。合法路径见 `references/fulltext-access.md`，实测可把覆盖率从 30% 提到 60% 以上。

### P2.5b Europe PMC（强烈建议，被低估的通道）

```bash
python scripts/fetch_epmc.py --works works.json --out epmc
```

这条路解决两个痛点，都不需要 PDF：

1. **付费墙论文的基金批准号**。Europe PMC 的 `grantsList` 返回 `agency` + `grantId`，即使论文完全闭源。实测 13 篇样本中，2 篇闭源论文的批准号就是从这里拿到的。
2. **结构化全文**。`inPMC=Y` 的论文可抓 JATS XML，直接给出基金段原文、伦理声明、数据可用性、作者贡献、收稿/接受日期、图表数量——比 PDF 更适合机器核对。

**两个坑**：`agency` 字段会录错（见过把国家基金标成某省基金），号码可信、机构名要核；`europepmc.org/articles/PMCxxx?pdf=render` 这类 PDF 渲染链接会 403，别用，走 `fullTextXML` 端点。

拿不到全文的三条正路（写进报告的建议栏）：

1. 通过所在单位图书馆的文献传递服务（覆盖 90%+，多数单位免费）
2. 直接联系通讯作者索取（学术惯例，回复率 50–70%）
3. 单篇购买（中文刊约 0.5–3 元，比英文刊便宜得多）

**注意**：若被审计对象本人就是通讯作者，**不要用作者索取这条路**——等于通知对方你在查他。改走图书馆传递。

**报告必须逐篇列出"全文未获取"清单**，并在依赖全文的维度标 D。不得因为"没看到"就默认正常——这是这类审计最常见的失职。

只有在拿到全文后才能做的核查：图片跨论文复用、伦理批号真实性、样本量与统计表一致性、正文数字与表格对应、审稿周期（原文 received/accepted 日期）。

### P2.6 基金号提取（有全文后必做）

```bash
python scripts/extract_grants.py --works works.json --fulltext fulltext --out grants
```

从已下载的 PDF 定位 Funding / Acknowledgments 段落，抽出 NSFC 批准号（8 位）与带标签的项目编号，连同原文摘录输出成待核表。

**这一步替掉的正是 D5 最耗时的人工活**——以前要逐篇打开 PDF、翻到文末、手抄号码，十几篇就是半小时；现在机器先筛，人只做核验。

三条纪律：

1. **提取结果一律标「待核」。** 脚本不做归属推断。批准号真实存在、负责人是否为本人、依托单位是否一致、执行期是否覆盖论文时间——四项必须到 `kd.nsfc.cn`（项目综合查询）人工核完。
2. **该站是 JS 应用，脚本抓不到结果。** 不要试图绕过，也不要凭号码格式猜年份和学部。编码规律会因学部、项目类型、延期与连续资助而失效，只能用来发现可疑，不能用作判据。
3. **无全文的篇目，D5 只能判 D。** 元数据里的 `funders` 只有机构名没有号码，据此判"合规"等于没查。

### P3 六维审核

```bash
python scripts/analyze_works.py --input works.json --watchlist watchlist.csv --out-prefix case01
```

脚本输出机器可读指标与规则化信号。**脚本给的是信号，不是结论**——每一维都要回到原文核对。评分卡与判定阈值见 `references/audit_rubric.md`。

| 维度 | 核心问题 | 必查动作 |
|---|---|---|
| D0 身份一致性 | 这些论文真的都属于本人吗 | 跑脚本的 `identity_check`，逐篇核对孤立论文的作者单位 |
| D1 产出节奏 | 产出规模与节奏是否可解释 | 年度分布 + 峰值年逐篇核对投稿/录用时间 |
| D2 专业相关性 | 是否超出本人专业 | 看 topic 层级是否有主线；跨域论文中本人是否主导 |
| D3 期刊质量 | 是否水刊/掠夺性期刊 | 逐刊核对收录状态、预警名单、APC、审稿周期 |
| D4 学术规范 | 是否代写/论文工厂/重复发表 | 图片比对、文本重合、PubPeer、伦理批号、注册号 |
| D5 基金合规 | 国自然标注是否真实合规 | 抄录每个基金号 → 基金委共享服务网逐一核验 |
| D6 成果一致性 | 履历/结题报告与公开论文是否对得上 | 拿申报材料与论文清单比对 |

D5 是最容易出硬结论、也最容易被元数据误导的一维：OpenAlex 的 `funders` 字段**没有基金批准号**，只有资助机构名。所以"基金号是否真实、是否属于本人项目"必须人工打开论文首页脚注抄录，再去 `kd.nsfc.gov.cn`（科学基金共享服务网）核对项目负责人与依托单位。不要用元数据直接下判断。

### P3.5 逐篇批注（选项 C 开启时）

```bash
python scripts/annotate_papers.py --works works.json --metrics metrics_metrics.json \
    --fulltext fulltext --out annotations --stamp
```

**脚本只写事实，不写判断。** 分工必须守住：

| 谁填 | 填什么 |
|---|---|
| 脚本 | 位次、期刊、ISSN、DOI、基金列表、主题层级、主线内外、全文状态、自动标记（误并/撤稿/无 DOI/多基金） |
| 审计人 | D2–D5 逐维结论、本篇定性、需本人说明事项、验证路径 |

脚本故意不写"是否可疑"——那必须基于原文比对得出，不能让元数据自动定罪。

**批注单是本报告最细的证据单元。** 举报场景下，每份批注单可直接作为"附件 N"，因为它自带 DOI、页码指向和事实陈述。

**PDF 批注页**：`--stamp` 会在每篇 PDF 前插一页 A4 批注页（标题、篇目编号、作者位次、7 项待核复选框、四档结论勾选框、审计人签名栏），另存为 `annotations/pdf/*_annotated.pdf`。**原始 PDF 字节不动**，这是证据完整性的底线——任何时候都要能出示未经修改的原始文献。

### P4 反向验证

对每个 B 级及以上疑点，写一段"如果这是正常的，会是什么样"：

- 跨专业 → 是否与本院其他科室/高校有长期合作？合作者在那些论文里是否为通讯？
- 高产 → 是否有大团队、是否为综述型作者、是否有共同一作机制？
- 单刊集中 → 是否该刊为所在学会会刊、是否为本领域常规投稿渠道？
- 多基金标注 → 是否为国家重点研发计划的子课题联合标注？

把反向证据写进报告。找不到反向证据时，明确写"已检索但未发现可解释的正常原因，检索范围为……"。

发现身份误并（D0 命中）时，先剔除该论文再重算全部指标，并在报告中保留剔除清单与理由。

### P5 报告产出

按 `references/report_spec.md` 的结构，用 `assets/report_template.md` 生成 Markdown 报告，再渲染 HTML：

```bash
python scripts/render_report.py --input report.md --output report.html --title "学术成果审计报告：<姓名>"
```

**交付 PDF**（举报、评审、内部报批基本只认 PDF）：

```bash
python scripts/render_pdf.py --input report.md --output report.pdf
# 宽表多时加 --landscape；换纸 --paper A3
```

`render_pdf.py` 调本机 Edge/Chrome 无头打印，纯标准库、无第三方依赖，中文与表格渲染已实测正常。找不到浏览器时会把 HTML 保留下来并提示手动 Ctrl+P，不会静默失败。**出 PDF 后必须自己打开看一遍**：中文有无乱码、表格有无被切断、页数与体积是否合理。

PDF 与 HTML 一起用 `present_files` 交付，PDF 放第一位。

报告与原始数据放同一目录，保证可复现：

```
audit_<姓名拼音>_<YYYYMMDD>/
├── report.md              # 主报告
├── report.html            # 可查看/可打印版本
├── cand.json              # 身份消歧候选与确认依据
├── works.json             # 论文全量元数据
├── metrics_metrics.json   # 指标与规则信号
├── metrics_metrics.md     # 指标摘要（可并入报告附录）
├── epmc/                  # Europe PMC 记录与 PMC 开放全文
│   ├── epmc_records.json
│   └── fulltext/*.xml
├── fulltext/              # 开放获取全文（选项 B）
│   ├── *.pdf
│   └── fulltext_manifest.md
├── grants/                # 基金号提取与待核表
│   └── grants_extracted.md
└── annotations/           # 逐篇批注（选项 C）
    ├── index.md
    ├── <年份>_<id>.md
    └── pdf/*_annotated.pdf
```

**举报用途的额外交付**：若委托用途为举报准备，另按 `references/case-playbook.md` 的第八节，把报告重排为三链结构（事实链 / 规则链 / 责任链），一事一节，并**主动附上剔除清单**——主动说明"这几篇经核查不属于本人，已排除"，是提高可信度最有效的一招。

交付前自检（逐项打勾，见 `references/red_lines.md` 第五节）：每条判断有来源？每个数字有口径？每个疑点有反向证据？有没有出现"确认造假"这类越界表述？

用 `present_files` 交付 HTML 报告（优先，便于查看与打印），同时附 Markdown。

## 四、判定语言对照

| 等级 | 含义 | 允许的表述 | 禁止的表述 |
|---|---|---|---|
| A | 未发现异常 | "在该数据源与检索范围内未发现异常" | "没有问题""清白" |
| B | 需说明的疑点 | "存在需本人说明的情况""建议补充说明" | "有问题""不正常" |
| C | 高度可疑 | "多项独立信号指向同一问题，建议移送核查" | "造假""代写""学术不端成立" |
| D | 证据不足 | "公开数据不足以判断""需调取原始数据" | "大概""应该是" |

## 五、参考资料

- `references/audit_rubric.md` — 六维评分卡、判定阈值、每维的常见误判
- `references/case-playbook.md` — 举报实战核查手册（三链结构、基金五要素、虚假结题交叉核查、30 分钟验证原则、常见退回原因）
- `references/fulltext-access.md` — 全文合法获取路径（Europe PMC API、PMC XML、机构传递、作者索取），含实测覆盖率
- `references/data_sources.md` — 数据源清单、中英文检索式、各库覆盖盲区
- `references/red_lines.md` — 表述纪律、法律边界、举报材料规范
- `references/report_spec.md` — 报告章节结构与写作要求
- `assets/report_template.md` — 报告模板
- `assets/watchlist_template.csv` — 期刊预警名单导入模板
