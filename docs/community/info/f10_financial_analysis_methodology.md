# F10 财务分析方法论与 TradingAgents 接入评估

生成日期：2026-05-09

## 资料来源

本方法论整理自以下本地课程笔记：

- `/Users/cong.zhou/Documents/quantitative/caibaofenxi/财务报表分析实战指南：从入门到精通的F10课程核心内容.md`
- `/Users/cong.zhou/Documents/quantitative/caibaofenxi/股票市盈率（PE）估值方法入门：不同行业PE合理区间与应用陷阱解析.md`
- `/Users/cong.zhou/Documents/quantitative/caibaofenxi/市净率(PB)估值法深度解析：适用场景、行业应用与实战策略.md`
- `/Users/cong.zhou/Documents/quantitative/caibaofenxi/F10估值体系第二课：PEG成长估值法的计算、应用与避坑指南.md`
- `/Users/cong.zhou/Documents/quantitative/caibaofenxi/F10课程第五讲：PS（市销率_营收倍数）估值方法精讲与A股案例分析.md`
- `/Users/cong.zhou/Documents/quantitative/caibaofenxi/F10投资课程：彻底搞懂净资产收益率ROE，用杜邦分析法拆解不同商业模式的选股逻辑.md`

## 核心原则

财务分析不能先套指标，而是先判断公司类型，再选择估值和质量检查方法。

错误路径：

```text
看到 PE/PB/ROE 数值 -> 直接判断便宜或贵
```

正确路径：

```text
识别行业和商业模式 -> 检查三大报表质量 -> 选择 PE/PB/PEG/PS/ROE/杜邦分析 -> 输出估值结论和风险点
```

## 一、公司类型识别

第一步是判断公司属于哪类资产，因为不同资产的定价锚不同。

| 公司类型 | 典型行业 | 核心定价锚 | 优先方法 |
| --- | --- | --- | --- |
| 稳定盈利龙头 | 白酒、消费、医药器械、部分公用事业 | 利润确定性、ROE、现金流 | ROE、PE、现金流质量 |
| 资产驱动公司 | 银行、保险、券商、地产 | 净资产质量、资产回报率 | PB、ROE、资产质量 |
| 强周期公司 | 钢铁、煤炭、有色、化工、养殖 | 周期位置、资产安全边际 | PB、周期位置，谨慎使用 PE |
| 高成长公司 | 半导体、AI、机器人、高端制造、军工 | 未来 1-3 年盈利增速 | PEG、PE、研发和订单验证 |
| 亏损或利润被压低公司 | 创新药、AI 应用、云计算、早期科技 | 营收增速、毛利率、盈利路径 | PS、毛利率、营收增速 |
| 博弈属性强的股票 | 次新股、纯题材股 | 流动性、筹码、情绪 | 财务估值仅作底线检查 |

结论：TradingAgents 做财务分析前必须先输出“公司类型判断”，否则后续估值工具容易误用。

## 二、三大报表质量检查

三大报表用于回答三个基础问题：

| 报表 | 回答的问题 | 关键字段 |
| --- | --- | --- |
| 利润表 | 公司是否真的赚钱，利润来自哪里 | 营业收入、营业成本、毛利率、净利润、归母净利润、研发费用、销售费用、管理费用 |
| 资产负债表 | 公司家底和杠杆是否健康 | 货币资金、应收账款、存货、总资产、总负债、净资产、短期负债、合同负债 |
| 现金流量表 | 利润是否变成现金 | 经营现金流、投资现金流、筹资现金流、现金及等价物变化 |

重点检查：

- 营收增长但毛利率持续下滑，可能是价格战或产品竞争力下降。
- 净利润增长但经营现金流跟不上，可能是纸面利润。
- 应收账款和存货显著增加，需要判断是否存在收入确认激进或库存积压。
- 短债、总负债和资产负债率上升，需要判断偿债压力。
- 研发费用、合同负债、在手订单可用于判断成长股后续兑现能力。

## 三、ROE 与杜邦分析

ROE 是股东资金使用效率，但不能只看单一年份数值。必须拆解 ROE 来源。

```text
ROE = 销售净利率 × 总资产周转率 × 权益乘数
```

| ROE 来源 | 含义 | 代表类型 | 风险 |
| --- | --- | --- | --- |
| 高销售净利率 | 定价权、品牌、技术壁垒 | 白酒、高端医药、软件 | 需求下滑或竞争破坏定价 |
| 高资产周转率 | 供应链和运营效率 | 家电、零售、快消 | 毛利薄、竞争激烈 |
| 高权益乘数 | 高杠杆撬动利润 | 银行、地产、建筑 | 负债压力和资产质量风险 |

需要识别的假高 ROE：

- 一次性收益导致的高 ROE。
- 连续亏损后净资产缩水导致的高 ROE。
- 高杠杆堆出来的高 ROE。
- 经营现金流远低于净利润的纸面利润。

## 四、PE 估值

PE 适用于利润相对稳定、盈利质量可验证的公司。

```text
PE = 总市值 / 净利润
```

使用 PE 时必须结合：

- 行业属性。
- ROE 水平。
- 盈利增速。
- 利率环境。
- 市场成交量和风险偏好。

使用边界：

| 行业类型 | PE 是否适用 | 说明 |
| --- | --- | --- |
| 食品饮料、稳定消费 | 适用 | 需结合 ROE、分红和增速 |
| 医药成熟龙头 | 较适用 | 创新药需额外看管线和研发 |
| 银行、地产 | 参考弱 | 更适合 PB |
| 强周期 | 容易误导 | 周期顶部 PE 可能很低，反而危险 |
| 高科技成长 | 不能孤立看 | 高 PE 要结合未来增速和 PEG |

## 五、PEG 成长估值

PEG 用于判断成长股“价格相对增速是否划算”。

```text
PEG = PE / 未来盈利增速
```

使用要求：

- G 应优先使用未来 1-3 年预期盈利增速，而不是简单用历史增速。
- 适合盈利增速可预测的成长股。
- 市场成交量越高，PEG 容忍度越高；缩量环境下 PEG 标准必须收紧。
- PEG 只判断性价比，不判断公司长期质地。

适用：

- AI 算力、半导体设备、创新药、高端制造、机器人、消费电子、军工等。

不适用：

- 银行、地产、煤炭、钢铁、公用事业、靠分红的低增长公司。

## 六、PB 估值

PB 用于判断资产驱动公司的资产安全边际。

```text
PB = 总市值 / 净资产
```

合理 PB 需要结合：

- ROE。
- 净资产质量。
- 资产减值风险。
- 周期位置。
- 利率环境。

适用：

- 银行、保险、券商、地产、钢铁、煤炭、有色、资源股。

风险：

- 破净不等于低估，可能是资产质量差。
- 周期下行时 PB 可能继续下降。
- 科技公司很多核心价值不在账面净资产，PB 参考意义弱。

## 七、PS 估值

PS 是 PE 失效时的过渡工具。

```text
PS = 总市值 / 营业收入
```

适用场景：

- 公司亏损，PE 无法计算。
- 利润被研发投入压低。
- 商业模式重构期。
- 营收快速增长但利润尚未释放。

PS 必须配合：

- 毛利率。
- 营收增速。
- 未来净利率提升路径。
- 行业空间。
- 竞争格局。
- 何时能切换回 PE 估值。

误区：

- PS 不是越低越便宜。
- 低毛利、低增速公司的低 PS 可能是价值陷阱。
- 高 PS 依赖持续高增速，增速不及预期会快速杀估值。

## TradingAgents 财务分析推荐流程

后续应要求 TradingAgents 按下面固定流程输出财务分析：

```text
1. 公司类型识别
2. 三大报表质量检查
3. 盈利能力分析：毛利率、净利率、ROE
4. 杜邦拆解：净利率、资产周转率、权益乘数
5. 增长质量检查：营收、利润、现金流是否同步
6. 资产负债风险检查：现金、应收、存货、负债
7. 估值方法选择：PE / PB / PEG / PS
8. 结合行业、利率、成交量调整估值容忍度
9. 输出低估/合理/高估/不可估判断
10. 输出风险点和下一期财报需要跟踪的字段
```

## 方法反推字段需求

| 方法模块 | 必须字段 | 增强字段 |
| --- | --- | --- |
| 公司类型识别 | 行业、主营业务、交易所、板块 | 概念、产业链位置、同业公司 |
| 三大报表质量 | 营收、净利润、总资产、总负债、净资产、经营现金流、应收、存货 | 费用明细、合同负债、受限资金、短债 |
| ROE/杜邦 | ROE、净利率、总资产周转率、权益乘数、总资产、净资产 | 加权 ROE、ROIC、ROA |
| 现金流质量 | 经营现金流、净利润 | 净现比、自由现金流、现金含量历史趋势 |
| PE | 市值、净利润、EPS、股价 | 一致预期 EPS、分红率、利率 |
| PB | 市值、净资产、每股净资产 | 资产减值、拨备覆盖率、资本充足率 |
| PEG | PE、未来盈利增速 | 券商一致预期 EPS、未来 1-3 年利润预测 |
| PS | 市值、营收、毛利率、营收增速 | 目标净利率、研发费用率、订单/合同负债 |
| 行业比较 | 行业分类、同业估值、行业均值 | 行业分位数、历史估值分位数 |
| 市场环境 | 全市场成交额、利率、benchmark | 风险偏好、行业成交额、资金流 |

## 当前 TradingAgents 是否已使用该方法

结论：已经接入第一版 F10 方法论约束和确定性分析底稿，但估值、行业同业、预测数据仍需要后续补齐。

当前 `vnpy_tradingagents/prompts.py` 的 worker prompt 已约束：

- 只能使用 `request.context` 中的 PostgreSQL 快照。
- 遵守 A 股交易时间、T+1、涨跌停、风控和不得直接下单等规则。
- 输出 `rating/confidence/action/report/risk_notes`。
- 财务分析必须按 F10 方法先判断公司类型，再选择 PE/PB/PEG/PS。
- 财务分析必须检查三大报表、杜邦、现金流质量、估值方法适用性和字段缺失。

第一版新增了确定性 `F10FinancialAnalyzer`：

- 从 `context["financials"]["statements"]` 和 `context["financials"]["indicators"]` 读取三大报表和指标。
- 生成 `context["f10_financial_analysis"]`，包含公司类型、盈利能力、资产负债、现金流质量、杜邦拆解、成长质量、估值方法可用性和缺失字段。
- 修复了 TradingAgents 单表工具读取路径，`get_context_balance_sheet/cashflow/income_statement` 可读取 `financials.statements.*`。
- 扩展了 `FundamentalSnapshotBuilder`，支持 AKShare/东方财富字段：`OPERATE_INCOME`、`NETPROFIT`、`NETCASH_OPERATE`、`TOTAL_ASSETS`、`TOTAL_LIABILITIES`、`ROEJQ`、`XSMLL`、`XSJLL`、`ZCFZL`、`BPS`、`EPSJB`。

仍然需要注意：当前只是“方法论约束 + 本地计算底稿”，不是完整估值系统。PE/PB/PS/PEG 的市场估值数据、行业同业分位、未来一致预期还没有完整接入，因此 TradingAgents 必须在这些字段缺失时输出 degraded。

## 是否可以形成 skill 或 prompt

已经按两层实现第一版。

### 第一层：Prompt 约束

已新增 `F10_FINANCIAL_ANALYSIS_PROMPT`，并合入 `build_worker_system_prompt()`。

要求 TradingAgents 在财务分析时必须按以下结构输出：

```text
一、公司类型和适用估值法
二、三大报表质量
三、ROE 和杜邦拆解
四、现金流质量和资产负债风险
五、估值分析：PE/PB/PEG/PS 中选择适用方法
六、字段缺失和分析降级
七、结论：低估/合理/高估/不可估 + 风险点
```

优点：改动小，可以先落地。

缺点：指标计算仍由 LLM 自行理解，容易受字段命名影响。

### 第二层：确定性财务分析 skill/context builder

已新增一个确定性分析层：

```text
F10FinancialAnalyzer
```

职责：

- 从 `financial_statement_snapshot` 和 `financial_indicator_snapshot` 中计算标准指标。
- 输出统一字段：`roe`、`gross_margin`、`net_margin`、`asset_turnover`、`equity_multiplier`、`cash_profit_ratio`、`debt_to_assets`、`revenue_yoy`、`net_profit_yoy` 等。
- 判断适用估值方法。
- 把“计算好的分析底稿”传给 TradingAgents，而不是让 LLM 直接在原始字段里猜。

## 当前落库字段覆盖情况

### 已落库且较完整

`financial_statement_snapshot` 已保存三大报表 raw fields，当前样例中包含：

- 利润表：`OPERATE_INCOME`、`TOTAL_OPERATE_INCOME`、`NETPROFIT`、`PARENT_NETPROFIT`、`BASIC_EPS`、`RESEARCH_EXPENSE`、`SALE_EXPENSE`、`MANAGE_EXPENSE`。
- 资产负债表：`TOTAL_ASSETS`、`TOTAL_LIABILITIES`、`TOTAL_EQUITY`、`TOTAL_PARENT_EQUITY`、`MONETARYFUNDS`、`ACCOUNTS_RECE`、`INVENTORY`、`TOTAL_CURRENT_ASSETS`、`TOTAL_CURRENT_LIAB`、`SHARE_CAPITAL`。
- 现金流量表：`NETCASH_OPERATE`、`NETCASH_INVEST`、`NETCASH_FINANCE`、`END_CCE`、`SALES_SERVICES`。

`financial_indicator_snapshot` 已保存财务指标 raw fields，当前样例中包含：

- `ROEJQ`：净资产收益率。
- `XSMLL`：销售毛利率。
- `XSJLL`：销售净利率。
- `ZCFZL`：资产负债率。
- `TOAZZL`：总资产周转相关指标。
- `YSZKZZL`、`YSZKZZTS`：应收账款周转相关指标。
- `CHZZL`、`CHZZTS`：存货周转相关指标。
- `JYXJLYYSR`、`NCO_NETPROFIT`：现金流质量相关指标。
- `BPS`：每股净资产。
- `EPSJB`：基本每股收益。

`financial_report_document` 已保存部分官方报告 PDF 元数据：

- `600519.SSE` 和 `688008.SSE` 有 CNINFO PDF 元数据。
- `000001.SZSE` 本次没有匹配到官方 PDF，但结构化报表和指标已入库。

### 已传给 TradingAgents

`MarketDataToolkit` 当前会传：

- `context["financials"]["statements"]`
- `context["financials"]["indicators"]`
- `context["financials"]["documents"]`
- `context["fundamentals"]`
- `context["valuation"]`

其中 `financials` 包含较完整 raw fields，`f10_financial_analysis` 提供可审计的 F10 分析底稿。

`fundamental_snapshot` 已扩展摘要字段映射：

- `revenue`、`net_profit`、`operating_cash_flow`、`total_assets`、`total_liabilities`。
- `roe`、`gross_margin`、`net_margin`、`debt_to_assets`、`asset_turnover`。
- `bps`、`eps`。

### 目前缺失或不完整

| 方法需求 | 当前状态 | 影响 |
| --- | --- | --- |
| PE/PB/PS/PEG | `valuation_snapshot` 仍为 `degraded`，缺少市值、PE、PB、PS、PEG | 不能系统性做估值判断 |
| 公司类型识别 | 缺少稳定行业/主营业务/板块/同业分类上下文 | 难以自动选择估值方法 |
| 杜邦拆解 | 已计算第一版 `net_margin × asset_turnover × equity_multiplier` | 缺少多期趋势和同业对比 |
| 现金流质量 | 已计算经营现金流/净利润 | 缺少自由现金流、历史趋势和同行对比 |
| 成长质量 | 有部分 YOY 字段和多期数据，但未标准化趋势 | PEG 和成长判断不稳定 |
| 未来一致预期 | 没有券商一致预期 EPS/利润增速 | PEG 只能用历史增速近似，不够严格 |
| 市场环境 | 缺少全市场成交额、利率、风险偏好 | 无法按课程方法调整估值容忍度 |
| 官方 PDF 全文 | 当前只存 PDF 元数据，未解析正文 | 无法读取管理层讨论、风险提示、分红计划 |
| 财务工具函数路径 | 已适配 `financials.statements.*` 嵌套结构 | 后续需要继续覆盖更多 upstream tool 名称别名 |

## 下一步建议

1. 增加估值 provider，补齐市值、PE、PB、PS、股价、总股本、流通股本。
2. 增加行业/同业 provider，支持行业估值区间、同业比较和历史估值分位。
3. 增加一致预期或预测数据源，否则 PEG 只能降级为历史增速估算。
4. 扩展 `F10FinancialAnalyzer` 的多期趋势能力，补充营收、利润、经营现金流、应收、存货、负债的历史趋势判断。
5. 后续解析官方 PDF 正文，补充管理层讨论、风险提示、分红计划、订单和研发信息。
