# 数据源、检索式与覆盖盲区

## 一、检索留痕规范

报告的方法节必须能让人复现检索。每条检索记录包含五项：

```
数据源 | 检索式 | 检索日期 | 命中数 | 纳入数
```

例：
```
OpenAlex API | filter=display_name.search:San Zhang,affiliations.institution.id:I000000000 | 2026-11-12 | 4 | 1
CNKI 作者检索 | 作者=张三 AND 单位=示例大学 | 2026-11-12 | 23 | 19（去重后）
```

未记录检索式的结论视为不可复现，不得写入报告结论节。

---

## 二、英文/国际数据源

### OpenAlex（主数据源，脚本已集成）
- 入口：`https://api.openalex.org`
- 能力：作者消歧档案、全量作品、主题分类（topic→subfield→field→domain）、基金资助方、撤稿标记、OA 状态、作者位次
- 关键端点：
  - `/authors?filter=display_name.search:<name>,affiliations.institution.id:<iid>`
  - `/institutions?search=<机构中文名或英文名>` — **支持中文**，是解析中文单位的关键
  - `/works?filter=author.id:<aid>&cursor=*`
- 盲区：
  - 中文期刊收录不全，非核心刊几乎缺失
  - `funders` 只有机构名，**没有基金批准号**
  - 作者消歧存在错误合并与漏合并，必须做 D0 检查
  - `grants` 字段不可通过 `select` 请求，默认常返回 null
- 礼貌池：请求带 `mailto`，每秒 ≤10 次

**中文拼音姓名的四个坑（实测踩过，务必避开）**

| 坑 | 表现 | 对策 |
|---|---|---|
| `/authors?search=<拼音名>` 几乎不可用 | 返回大量无关同名者（搜 "Jianping Qi" 会返回 "Li J""Jianmin Wu"），按论文量排序会把这些高产的排到最前 | 一律用 `filter=display_name.search:<名>`，不要用 `search` |
| `raw_author_name.search` 会做近似匹配 | 「Jianping Qi」命中了含「Jianping Xie」「Qi Xia」的论文，看起来命中 1 篇，实际无关 | **凡命中必逐个核对作者列表**，不能只看 hitCount |
| 拼音重名率远超预期 | 「Jianping Qi」在 OpenAlex 至少两人（复旦药学院 169 篇 + 其他人），不限定机构必错 | 机构过滤是必需项，不是可选项 |
| 机构更名后新名常无记录 | 机构升格改名后，新名在 OpenAlex 可能 count=0，必须用旧名检索 | 先 `/institutions?search=` 探一次，count=0 时换历史名称 |

**排查顺序**（查不到人时按此走）：
1. `/institutions?search=<中英文名>` 确认机构在库、拿到 institution id
2. `filter=display_name.search:<名>,affiliations.institution.id:<id>`
3. 换姓名变体（西文姓名顺序：`Mingming Zhang` / `Zhang Mingming` / `Mingming-Zhang`）
4. 仍为 0 → 换 `raw_affiliation_strings.search:<机构英文名>` 做论文级反查
5. 论文级命中 → **打开作者列表核对**，确认该姓名确实属于该单位
6. 全部为 0 → 结论只能是「该数据源未检索到记录」，**不能推断为「无学术成果」**

### Crossref
- 入口：`https://api.crossref.org/works?query.author=<name>`
- 能力：DOI 权威元数据、出版者、funder 信息（含 award 编号，比 OpenAlex 全）
- 盲区：限速严格（易 429），需退避；中文刊覆盖有限
- 用途：**补充基金批准号**。`message.funder[].award` 常含批准号，是 D5 的重要交叉源

### PubMed / Europe PMC
- 入口：`https://pubmed.ncbi.nlm.nih.gov/?term=<query>`、`https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=`
- 检索式：`"Zhang San"[Author] AND "Example"[Affiliation]`
- 能力：生物医学全文、伦理声明、临床试验注册号、基金字段（部分）
- 盲区：示例学科中文刊覆盖差；Europe PMC 有 REST API 可批量取

### Semantic Scholar
- 入口：`https://api.semanticscholar.org/graph/v1/author/search?query=<name>`
- 能力：引用网络、作者影响力、论文撤稿标记
- 盲区：需 API key 才稳定；作者合并错误率较高

### Retraction Watch Database
- 入口：`http://retractiondatabase.org`（现由 Crossref 托管，可通过 Crossref API 查 `update-to` 关系）
- 能力：撤稿记录、撤稿原因、原始论文与撤稿声明的关联
- 用法：按作者名或 DOI 查；**必须读撤稿声明原文判断原因性质**

### PubPeer
- 入口：`https://pubpeer.com/search?q=<doi 或作者名>`
- 能力：同行质疑、图片重复指控、作者回应
- 注意：PubPeer 条目属**公开质疑**，不是认定。引用时必须写明"存在公开质疑，未见期刊处理结论"

### ORCID
- 入口：`https://orcid.org/orcid-search/search?searchQuery=<name>`
- 能力：最可靠的身份锚点，含教育经历、任职、作品列表
- 用途：P1 消歧的首选标识

### Web of Science Master Journal List / Scopus Sources
- 入口：`https://mjl.clarivate.com`、`https://www.scopus.com/sources`
- 能力：期刊是否被 SCIE/ESCI/Scopus 收录、收录起止年、是否被剔除
- 用途：D3 判定"是否正规索引期刊"的权威依据

### DOAJ
- 入口：`https://doaj.org/search/journals`
- 能力：正规开放获取期刊白名单
- 用途：区分"正规 OA"与"掠夺性 OA"

### Scimago Journal Rank
- 入口：`https://www.scimagojr.com`
- 能力：期刊自引率、国家分布、逐年影响力
- 用途：自引率异常（>40%）是 D3 的辅助信号

---

## 三、中文数据源

### 中国知网（CNKI）
- 入口：`https://kns.cnki.net`
- 检索式：`作者=张三 AND 作者单位=示例大学`
- 能力：中文期刊全量、作者机构、基金标注（页面显示）、被引、下载量
- 盲区：需登录/机构权限；反爬严格；无公开 API
- 用途：**中文成果的主力补检源**，OpenAlex 的最大盲区靠它填

### 万方数据
- 入口：`https://www.wanfangdata.com.cn`
- 检索式：`作者:(张三) * 作者单位:(示例大学)`
- 能力：学位论文（重要！知网外的学位论文覆盖更好）、会议论文、专利
- 用途：查学位论文与会议论文，判断是否存在学位论文拆分发表

### 维普
- 入口：`http://www.cqvip.com`
- 能力：中文期刊补充覆盖，部分刊物仅维普收录
- 用途：交叉验证中文论文是否漏检

### 百度学术
- 入口：`https://xueshu.baidu.com`
- 能力：跨库聚合、引用关系、作者主页
- 用途：快速摸底；数据准确性低于源库，仅作线索

### 国家新闻出版署期刊查询
- 入口：`https://www.nppa.gov.cn`（期刊/报纸查询）
- 能力：CN 号是否真实、期刊是否合法登记、主办单位
- 用途：D3 核验中文期刊是否为"非法出版物""内部资料"

### 中国临床试验注册中心（ChiCTR）
- 入口：`http://www.chictr.org.cn`
- 能力：注册号真实性、注册时间、研究方案
- 用途：D4-6 核验临床研究注册号

---

## 四、基金核查

### 科学基金共享服务网
- 入口：`https://kd.nsfc.gov.cn`（成果检索）、`https://output.nsfc.gov.cn`（大数据知识管理门户）
- 能力：按批准号/姓名/单位查已结题项目、项目负责人、依托单位、起止年月、资助金额、成果列表
- 检索式：批准号精确查；或 `负责人=姓名 AND 依托单位=单位`
- 盲区：
  - 只公开**已结题**项目，在研项目多不公开
  - 结题报告全文不公开，仅部分成果列表
  - 青年基金/面上项目均有收录，但部分专项不公开
- 判定要点：批准号格式（如 12345678 = 8 位，前两位为学部代码+年份段）、负责人姓名、依托单位三者必须同时匹配

### 国家重点研发计划
- 入口：`https://service.most.gov.cn`
- 用途：核查标注"国家重点研发计划"的项目编号

---

## 五、期刊评价名单

### 中科院《国际期刊预警名单》
- 发布方：中国科学院文献情报中心
- 获取：官方微信公众号/官网年度发布，通常年初
- **重要**：名单逐年调整，报告中必须注明版本年份。不得凭记忆列出刊名，必须核对当期官方文本
- 用法：把当期名单整理为 CSV（`assets/watchlist_template.csv` 格式），用 `--watchlist` 传给脚本

### 中科院期刊分区表
- 入口：`https://www.fenqubiao.com`（需机构订阅）
- 用途：D6 核验申报材料中的分区表述是否准确

### 北大《中文核心期刊要目总览》
- 用途：中文刊质量判定基准，注意版本年份（每 3 年更新）

### CSSCI / CSCD
- 用途：人文社科 / 自然科学中文核心的权威列表

---

## 六、覆盖盲区总表（必须写进报告）

| 盲区 | 影响维度 | 应对 |
|---|---|---|
| OpenAlex 中文刊覆盖不全 | D1 产出量、D2 专业分布 | CNKI/万方补检，报告中注明"中文成果经补检" |
| 元数据无基金批准号 | D5 全部 | 打开论文 PDF 首页脚注人工抄录 |
| 作者消歧错误合并 | D0/D1/D2 全部 | 跑 identity_check，逐篇核原文 |
| 撤稿记录同步滞后 | D4 | 交叉核对期刊官网 + PubPeer |
| 全文不可得（付费墙） | D4 图片/数据核查 | 标注为 D 档"证据不足"，不推测 |
| 在研项目不公开 | D5 | 注明"该项目可能为在研，未公开" |
| 会议摘要/增刊不在数据库 | D1/D6 | 从单位官网、申报材料反查 |
| 代写无法由公开数据证明 | D4 定性 | 只输出"与代写模式一致的特征"，不定性 |

**报告必须包含此表的相关行**，否则等于隐瞒方法局限。
