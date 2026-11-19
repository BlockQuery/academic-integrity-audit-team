# 全文获取路径（合规版）

审计需要全文，但**不是所有全文都能合法拿到**。这份文档解决一个实际问题：在不绕付费墙的前提下，怎么把覆盖率从 30% 提到 80% 以上。

## 一、不做的事

- 不使用 Sci-Hub 等盗版镜像
- 不借用他人或机构的账号凭证
- 不破解、不伪造 referer/cookie 绕过鉴权
- 不抓取出版社的付费页面

原因很实际：审计报告的用途往往是举报、评审、纪律程序。**如果证据本身来路不正，对方只要指出这一点，整份材料的可信度就会崩塌**——这比少几篇全文的损失大得多。

---

## 二、合法路径清单（按性价比排序）

| # | 路径 | 覆盖率贡献 | 成本 | 适用 |
|---|---|---|---|---|
| 1 | **Europe PMC 公开 API** | 高（生物医学 80%+） | 免费、秒级 | 有 DOI 的生物医学论文 |
| 2 | **PMC 开放子集全文** | 中（20–40%） | 免费 | 受 NIH/Wellcome 等资助的论文 |
| 3 | **OpenAlex 的全部 locations** | 中（常被忽略） | 免费 | 有机构库副本的论文 |
| 4 | **机构图书馆文献传递** | 高（90%+） | 免费或 2–5 元/篇 | 有单位归属的人 |
| 5 | **作者索取** | 中（50–70% 回复率） | 免费 | 有通讯邮箱的论文 |
| 6 | **预印本服务器** | 视学科 | 免费 | arXiv / bioRxiv / medRxiv / SSRN / Research Square |
| 7 | **国家科技图书文献中心 NSTL** | 高 | 约 3–10 元/篇 | 国内个人可注册 |
| 8 | **期刊开放存档** | 低但稳定 | 免费 | 部分期刊 12–24 个月后开放 |
| 9 | **基金委结题报告** | 特殊用途 | 免费 | 查成果清单，不是查论文 |

---

## 三、Europe PMC：审计场景下最被低估的工具

**它解决两个核心痛点**：

### 痛点 1：付费墙论文的基金号

论文 PDF 拿不到，但 Europe PMC 的公开 API 会返回 `grantsList`，**含资助机构与批准号**。这是经过 PubMed 人工/半自动录入的数据，可靠性高于 OpenAlex 的 `funders`（后者只有机构名）。

```
https://www.ebi.ac.uk/europepmc/webservices/rest/search
  ?query=DOI:"10.1155/2022/7571066"
  &resultType=core&format=json
```

返回里看三个字段：
- `grantsList.grant[].grantId` — 批准号
- `grantsList.grant[].agency` — 资助机构
- `isOpenAccess` / `inPMC` — 是否有开放全文

**注意一个坑**：`agency` 字段会录错。实测见过把国家自然科学基金（8 位号）标成 "Natural Science Foundation of Example Province"。**号码可信，机构名要交叉核对**。引用时以论文原文脚注为准。

### 痛点 2：没有 PDF 也要看正文

`inPMC=Y` 的论文可以直接拿结构化全文：

```
https://www.ebi.ac.uk/europepmc/webservices/rest/PMC9596273/fullTextXML
```

返回 JATS XML。对审计来说这**比 PDF 更好用**——结构化标签直接给出：
- `<funding-group>` 基金声明（原文，不是数据库转录）
- `<sec>` 标题里的 ethics / data availability / author contributions
- `<pub-date pub-type="received">` 和 `"accepted"` → 算审稿周期
- `<fig>` / `<table-wrap>` 计数 → 核对图表数量是否与正文引用一致

**PDF 渲染链接会 403，别浪费时间**（`europepmc.org/articles/PMCxxx?pdf=render` 需要浏览器会话）。XML 端点稳定。

---

## 四、OpenAlex 的 locations：一个容易漏的富矿

多数人只读 `best_oa_location`。但一篇论文可能有多个存放位置：

```json
"locations": [
  {"is_oa": false, "pdf_url": null, "landing_page_url": "https://doi.org/..."},
  {"is_oa": true,  "pdf_url": "https://repository.xxx.edu/bitstream/...pdf"}
]
```

`best_oa_location` 有时为空（判为 closed），而 `locations` 里其实躺着机构库的 OA 副本。**遍历全部 locations 逐个试**，能多捞出一批。

---

## 五、机构图书馆文献传递：覆盖率最高的正路

如果你有医院或高校的工号/学号，这条路能拿到 90% 以上，包括中文期刊。

**流程**（各家大同小异）：

1. 登录单位图书馆 → 找到"文献传递"或"馆际互借"入口
2. 填写：篇名、作者、刊名、年卷期页、DOI
3. 提交，通常 1–3 个工作日发到邮箱
4. 费用：多数单位对本校人员免费或补贴，校外约 2–5 元/篇

**CALIS / CASHL** 是全国性系统，成员馆之间互借。个人用户可通过所在单位图书馆代理申请。

**关键提示**：一次提交多篇时，把"最关键的 5 篇"排在前面。审计不需要全部，只需要支撑结论的那几篇。

---

## 六、作者索取：成功率比想象的高

学术界的惯例是：**索取单篇论文，作者基本都会给**。因为作者希望自己的研究被引用。

邮件模板（英文，直接抄）：

```
Subject: Request for full text: [论文标题] ([期刊], [年])

Dear Dr. [通讯作者姓],

I am conducting a research audit on [研究主题] and would like to
read your paper "[标题]" (DOI: [DOI]).

If you could share a PDF copy, I would be very grateful. I am happy
to use it solely for academic review purposes.

Thank you for your time.

Best regards,
[你的名字]
[单位]
```

**注意两点**：
- 用单位邮箱，回复率显著高于免费邮箱
- **如果被审计对象本人就是通讯作者，不要用这套模板**——那等于告诉对方你在查他。这种情况下走图书馆文献传递，或通过第三方（同事、合作者）索取。

---

## 七、中文论文：另一套渠道

| 渠道 | 覆盖 | 说明 |
|---|---|---|
| 知网（机构账号） | 最全 | 需单位订阅 |
| 万方 | 学位论文强 | 需单位订阅 |
| 国家哲学社会科学文献中心 | 社科类免费 | free |
| 中国科技论文在线 | 部分开放 | free |
| 维普 | 补充 | 需订阅 |

**如果没有任何机构账号**：知网的单篇付费约 0.5–3 元，比英文期刊便宜得多，直接买比找路径快。

中文期刊还有个特殊价值：**基金标注通常印在首页脚注**，而中文刊的目录页/摘要页往往免费可见，能先看到基金信息再决定要不要买全文。

---

## 八、优先级建议（按"审计目的"排）

不是所有论文都需要全文。按目的分配精力：

| 目的 | 需要的篇目 | 理由 |
|---|---|---|
| 核基金标注 | 只需**首页脚注**，不需要全文 | Europe PMC + 出版社摘要页的 Funding 字段就够 |
| 核图片复用 | 需要**含图页**（通常中后部） | 必须全文 |
| 核数据一致性 | 需要**方法与结果页** | 必须全文 |
| 核审稿周期 | 需要**首页的 received/accepted 日期** | 摘要页有时也有 |
| 核伦理批号 | 需要**方法学开头段** | 必须全文 |

**实操结论**：如果审计目标只是"基金标注是否合规"，**80% 的论文不需要下载 PDF**。Europe PMC 一条 API 就能解决。真正需要全文的，是怀疑图片复用的那几篇。

---

## 九、本次实测覆盖率（13 篇样本）

| 渠道 | 获取数 | 备注 |
|---|---|---|
| OpenAlex best_oa_location | 4 | 30.8% |
| Europe PMC grantsList（基金号） | 4 | **含 2 篇付费墙论文** |
| PMC 开放全文 XML | 4 | 与 PDF 部分重叠 |
| 合计可读全文 | **8 / 13** | 61.5% |
| 剩余 5 篇 | 0 | 需图书馆传递或作者索取 |

**关键结论**：Europe PMC 一条通道，把基金信息的覆盖率从"4 篇有全文才能看"提升到"付费墙论文也能拿到批准号"。这是本次最大的方法改进。

---

## 十、一句话总结

> 不要绕墙。墙外能拿到的，比你想的多——OpenAlex 的 locations、Europe PMC 的 grantsList、PMC 的 XML、机构图书馆的传递，四样加起来能覆盖 80% 以上。剩下的几篇，花几块钱或发一封邮件就解决了，比冒证据被质疑的风险划算得多。
