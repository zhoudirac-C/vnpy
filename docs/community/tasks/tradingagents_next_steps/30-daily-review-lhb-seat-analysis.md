# P30 每日复盘龙虎榜深度分析任务

目标：在 `每日市场复盘` 中补齐龙虎榜的机构/活跃营业部/疑似游资席位拆解、席位成功率、上榜原因分类和买卖集中度分析，并把这些结构化证据安全地提供给 AI 复盘提示词使用。

## 范围边界

- 本阶段只服务 `vnpy_daily_review` 的报告和明日观察计划，不直接下单。
- “游资”不是官方字段，只能基于活跃营业部名称、历史上榜统计、买卖偏好和席位行为做“疑似活跃资金/疑似游资席位”推断。
- 免费 AKShare/东方财富接口可能不稳定，所有 provider 失败都必须降级为质量告警，不能阻塞 vn.py 启动。
- 个股买卖席位明细不能全市场逐只拉取，第一版只对龙虎榜净买/净卖 Top N 和风向标候选做限量补充。
- AI 必须引用 Evidence ID，不允许把没有证据的席位标签、成功率或资金类型写成确定事实。

## 当前状态

- 已接入 `akshare.stock_lhb_detail_em(start_date, end_date)`。
- 已修复 `龙虎榜买入额`、`龙虎榜卖出额`、`龙虎榜净买额` 字段解析，提交：`671d7c06`。
- 当前复盘只使用龙虎榜净买合计和个股净买额加分。
- 当前尚未结构化接入：
  - 机构买卖拆解。
  - 活跃营业部/疑似游资拆解。
  - 席位成功率。
  - 上榜原因分类。
  - 买卖集中度。
  - 这些信息对应的 AI 提示词约束。

## AKShare 数据源规划

| 能力 | AKShare 接口 | 第一版用途 | 调用策略 |
| --- | --- | --- | --- |
| 龙虎榜总表 | `stock_lhb_detail_em(start_date, end_date)` | 总买卖额、净买额、上榜原因、占总成交比 | 每次复盘必拉 |
| 机构买卖统计 | `stock_lhb_jgmmtj_em(start_date, end_date)` | 买方机构数、卖方机构数、机构净买 | 每次复盘必拉 |
| 每日活跃营业部 | `stock_lhb_hyyyb_em(start_date, end_date)` | 活跃营业部、买入股票、营业部代码、总净买 | 每次复盘必拉 |
| 个股买卖席位明细 | `stock_lhb_stock_detail_em(symbol, date, flag)` | 买方/卖方席位 Top 明细 | 只对 Top N 标的拉取 |
| 个股上榜统计 | `stock_lhb_stock_statistic_em(symbol="近一月")` | 近期上榜次数、机构买卖次数、近月涨跌幅 | 可缓存，复盘时读取 |
| 营业部统计 | `stock_lhb_traderstatistic_em(symbol="近一月")` | 席位上榜次数、买入/卖出次数、成交金额 | 可缓存，复盘时读取 |

## 阶段任务

- [x] **P30-T01: 领域模型补齐**
  - 修改：`vnpy_daily_review/domain.py`
  - 测试：`tests/test_daily_market_review_lhb_seat_analysis.py`
  - 内容：
    - 新增 `DailyLhbInstitutionSnapshot`：`symbol/name/trade_date/buy_institution_count/sell_institution_count/institution_buy_amount/institution_sell_amount/institution_net_amount/list_reason/provider`。
    - 新增 `DailyLhbActiveSeatSnapshot`：`seat_name/seat_code/trade_date/buy_stock_count/sell_stock_count/buy_amount/sell_amount/net_amount/buy_symbols/provider`。
    - 新增 `DailyLhbStockSeatSnapshot`：`symbol/trade_date/side/seat_name/seat_code/amount/seat_success_rate/seat_type_hint/provider`。
    - 新增 `DailyLhbReasonCategory` 或分类函数输出字符串：`price_deviation/turnover/three_day_deviation/amplitude/st_or_risk/unknown`。
  - 验收：
    - 金额字段非负校验。
    - `seat_success_rate` 允许为空，但有值时必须在 `0-100`。
    - `symbol` 复用现有 `validate_symbol()`。

- [x] **P30-T02: Provider 拉取和解析**
  - 修改：`vnpy_daily_review/providers.py`
  - 测试：`tests/test_daily_market_review_lhb_seat_analysis.py`
  - 内容：
    - 新增 `_load_akshare_lhb_institution()` 读取 `stock_lhb_jgmmtj_em`。
    - 新增 `_load_akshare_lhb_active_seats()` 读取 `stock_lhb_hyyyb_em`。
    - 新增 `_load_akshare_lhb_stock_seats()` 对 Top N 标的调用 `stock_lhb_stock_detail_em(symbol, date, flag="买入"/"卖出")`。
    - 从 `解读` 中解析类似 `成功率48.16%` 的席位/机构成功率。
    - 从 `上榜原因` 分类出涨幅偏离、换手、三日异动、振幅、ST/风险等类型。
    - provider_records 记录 `lhb_institution_snapshot`、`lhb_active_seat_snapshot`、`lhb_stock_seat_snapshot` 的 row_count、耗时和错误。
  - 验收：
    - 任一细分接口失败不影响 `DailyReviewDataBundle` 返回。
    - 2026-05-11 smoke 能拉到机构统计和活跃营业部数据。
    - 限量个股席位明细不会对全市场逐只调用。

- [x] **P30-T03: 龙虎榜信号分析引擎**
  - 修改：`vnpy_daily_review/signals.py`
  - 测试：`tests/test_daily_market_review_lhb_seat_analysis.py`
  - 内容：
    - 新增 `LhbSeatAnalysisSignal`，包含：
      - `institution_top_buy_symbols`
      - `institution_top_sell_symbols`
      - `active_seat_top_buy`
      - `suspected_hot_money_seats`
      - `reason_category_counts`
      - `high_concentration_symbols`
      - `risk_tags`
    - 新增 `LhbSeatAnalysisEngine.calculate(...)`。
    - `LeaderScoringEngine` 在已有净买额基础上，额外考虑：
      - 机构净买强度。
      - 活跃席位净买强度。
      - 上榜原因风险，例如高换手、高振幅、连续异动。
      - 买卖集中度过高时增加风险标签，不直接加分。
  - 验收：
    - 机构净买强的标的能进入 leader evidence_payload。
    - 高换手/高集中度标的不会被误判为无风险强买。
    - 无龙虎榜细分数据时输出空信号和 `lhb_seat_detail_empty` 质量告警。

- [x] **P30-T04: Evidence Pack 接入**
  - 修改：`vnpy_daily_review/evidence.py`
  - 修改：`vnpy_daily_review/service.py`
  - 测试：`tests/test_daily_market_review_lhb_seat_analysis.py`
  - 内容：
    - 增加以下证据类型：
      - `lhb_institution_flow`
      - `lhb_active_seat_flow`
      - `lhb_stock_seat_detail`
      - `lhb_reason_category`
      - `lhb_concentration`
    - Evidence content 必须包含：标的、净买卖金额、席位/机构数量、上榜原因分类、成功率来源说明。
    - AI 输入只保留 Top N 高相关龙虎榜证据，避免 token 爆炸。
  - 验收：
    - `EvidencePack.to_llm_input()` 中能看到龙虎榜细分 evidence。
    - 每条龙虎榜判断都可以追溯到 `evidence_id`。
    - secret guard 对新增 evidence 仍生效。

- [x] **P30-T05: AI 提示词改造**
  - 修改：`vnpy_daily_review/ai.py`
  - 测试：`tests/test_daily_market_review_vnpy_app.py`
  - 内容：
    - `ThemeRotationAnalyst` 增加：分析主线时参考龙虎榜机构/活跃席位是否与板块共振。
    - `LeaderAnalyst` 增加：
      - 区分“机构推动”“活跃营业部推动”“疑似游资接力”“无龙虎榜确认”。
      - 对疑似游资只能写“疑似/活跃席位”，不得写成确定事实。
      - 必须引用 `lhb_*` evidence_id，否则不能给出龙虎榜驱动结论。
    - `RiskCritic` 增加：
      - 高换手、高振幅、净卖出、卖方集中、短期上榜过频需要提示风险。
      - 上榜原因属于 ST/风险类时必须提示规避。
    - `WatchPlanWriter` 输出 JSON 增加可选字段：
      - `lhb_summary`
      - `capital_type`
      - `concentration_risk`
      - `reason_category`
  - 验收：
    - 单测能断言 prompt 中包含“疑似游资不能写成确定事实”“必须引用 lhb evidence_id”。
    - Fake LLM 输出带新增字段时，watch_items 能保留并展示/落库。

- [x] **P30-T06: UI 展示增强**
  - 修改：`vnpy_daily_review/ui/widget.py`
  - 测试：`tests/test_daily_market_review_vnpy_app.py`
  - 内容：
    - 在 `市场信号` tab 中增加龙虎榜摘要：
      - 机构净买 Top。
      - 活跃营业部 Top。
      - 上榜原因分布。
      - 高集中度/高风险标的。
    - `明日观察` 表格可展示 `capital_type` 或 `lhb_summary`。
  - 验收：
    - 无细分数据时 UI 显示“龙虎榜细分数据缺失”，不空白、不报错。
    - 有数据时能看到结构化摘要，而不是只看到 audit 原始 dict。

- [x] **P30-T07: PostgreSQL 落库和历史回看**
  - 修改：`vnpy_daily_review/storage.py`
  - 修改：`vnpy_daily_review/models.py`（仅当现有 `daily_review_evidence` 不够用时）
  - 测试：`tests/test_daily_market_review_lhb_seat_analysis.py`
  - 内容：
    - 第一优先级复用 `daily_review_evidence` 存龙虎榜细分 evidence。
    - 如果需要保存原始 seat rows，再新增 `daily_review_lhb_snapshot`，并继续复用 vn.py `database.*` + Peewee `create_tables()`。
    - 历史报告加载时能恢复新增 watch item 字段。
  - 验收：
    - 历史报告重新打开后仍能看到龙虎榜摘要字段。
    - 不新增独立 DSN，不新增自建 migration runner。

- [x] **P30-T08: 真实 smoke 和验证落档**
  - 新增：`docs/community/ops/validation_results/<date>-daily-review-lhb-seat-analysis.md`
  - 测试命令：
    - `uv run --with pytest python -m pytest tests/test_daily_market_review_lhb_seat_analysis.py -q`
    - `uv run --with pytest python -m pytest tests/test_daily_market_review_vnpy_app.py -q`
    - `uv run --with ruff ruff check vnpy_daily_review tests/test_daily_market_review_lhb_seat_analysis.py tests/test_daily_market_review_vnpy_app.py`
    - `uv run python -m compileall vnpy_daily_review`
  - 真实 smoke：
    - `2026-05-11` 运行 provider。
    - 记录龙虎榜总表、机构统计、活跃营业部、个股席位明细 row_count。
    - 记录 AI 输入中 `lhb_*` evidence 数量。
  - 验收：
    - 验证文档列出成功项、失败项、耗时、接口 row_count、数据质量告警。
    - 文档明确免费接口不构成生产 SLA。

## AI 提示词原则

AI 每日复盘中所有龙虎榜相关结论必须遵守：

1. 没有 `lhb_*` Evidence ID，不写龙虎榜驱动结论。
2. “游资”只能写成“疑似游资/活跃营业部资金”，并说明依据。
3. 机构买卖以 AKShare/东方财富机构统计字段为准，不能从营业部名称推断机构。
4. 高买卖集中度既可能代表强承接，也可能代表次日兑现风险，必须交给 `RiskCritic` 复核。
5. 上榜原因属于 ST、连续异常波动、跌幅偏离、过高换手时，必须在观察计划里降低仓位或标记规避。

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |
| P30-T01 至 P30-T08 | 2026-05-11 | 本次提交 | `21 passed`、ruff、compileall、真实 AKShare smoke |

## 风险

- AKShare 东方财富接口可能限流或字段变更，需要 provider_records 和质量告警兜底。
- 席位成功率可能来自文本 `解读` 或历史统计推导，不是官方强字段，AI 报告必须注明“依据有限”。
- 个股席位明细接口逐只拉取成本较高，必须限制 Top N，避免复盘时间过长。
- 免费数据不能替代生产级付费行情/资讯服务，真实上线前仍需连续运行验证。
