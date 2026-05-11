# P29 每日市场复盘 vn.py App 任务

目标：把旧 `quantitative-try` 中的 AI 每日全市场复盘方案迁入当前 vn.py fork，并按 vn.py 的 App/Engine/UI 体系落地为独立“每日市场复盘”入口。该模块只生成报告和观察计划，不直接下单，不替代 TradingAgents 单票分析，也不替代 CTA 策略和回测。

## 范围边界

- 新增 `vnpy_daily_review` 包，采用 `BaseApp + BaseEngine + PySide Widget`。
- 在 `examples/veighna_trader/run.py` 注册 `DailyMarketReviewApp`。
- 复用 vn.py `database.*` 和现有 PostgreSQL，不新增独立 DSN。
- 后续数据源复用 vn.py Gateway/Datafeed、AKShare Gateway、新闻公告入库和 P28 财报上下文。
- 第一版 UI 不再只显示“复盘服务未配置”；必须接入 vn.py/AKShare provider，能生成一版确定性复盘报告。
- 每日市场复盘不得 import 或调用订单、Gateway 下单、OMS 下单接口。

## 阶段任务

- [x] **P29-T01: 文档迁入和 vn.py 化改写**
  - 新增：`docs/community/info/ai-module-roadmap.md`
  - 新增：`docs/community/info/daily-market-review-ai-technical-plan.md`
  - 修改：`docs/community/info/index.rst`
  - 验收：文档明确每日市场复盘不是 FastAPI 旧页面，不是 TradingAgents 单票分析，目标是 vn.py 独立 App。

- [x] **P29-T02: 新增 DailyMarketReview App 元数据**
  - 新增：`vnpy_daily_review/app.py`
  - 新增：`vnpy_daily_review/engine.py`
  - 新增：`vnpy_daily_review/__init__.py`
  - 验收：`DailyMarketReviewApp` 可被 vn.py MainWindow 识别，`display_name=每日市场复盘`。

- [x] **P29-T03: 新增 PySide 独立 UI**
  - 新增：`vnpy_daily_review/ui/widget.py`
  - 新增：`vnpy_daily_review/ui/__init__.py`
  - 新增：`vnpy_daily_review/ui/daily_review.svg`
  - 验收：UI 包含 `今日报告`、`明日观察`、`市场信号`、`验证复盘`、`配置` 五个 tab。

- [x] **P29-T04: 启动脚本注册**
  - 修改：`examples/veighna_trader/run.py`
  - 验收：vn.py 启动后 `功能` 菜单和左侧工具栏出现“每日市场复盘”。

- [x] **P29-T05: 第一版服务边界**
  - 目标：Engine 提供 `load_latest_report()`、`run_preview()`、`validate_next_day()` 的稳定边界。
  - 验收：未接复盘流水线时返回明确 `not_configured`，不抛异常，不影响 vn.py 启动。

- [ ] **P29-T06: 后续完整数据流水线**
  - 目标：接入全市场行情、板块、涨停生态、龙虎榜、分时异动、新闻公告和财报证据。
  - 验收：生成 Evidence Pack、Markdown 报告、明日观察计划，并写入 PostgreSQL。
  - 状态：进行中，已拆出 P29-T06.1 至 P29-T06.4。

- [x] **P29-T06.1: 迁移旧项目核心领域和信号层到 vn.py**
  - 新增：`vnpy_daily_review/domain.py`
  - 新增：`vnpy_daily_review/signals.py`
  - 新增：`vnpy_daily_review/evidence.py`
  - 验收：领域对象、市场宽度、板块轮动、涨停生态、龙虎榜资金、风向标评分和 Evidence Pack 已在 vn.py 包内可独立测试。

- [x] **P29-T06.2: 接入 vn.py/AKShare 只读 provider**
  - 新增：`vnpy_daily_review/providers.py`
  - 验收：优先读取 vn.py 当前 tick；没有 tick 时降级读取 AKShare 全市场行情、板块和涨停池。provider 失败只记录质量，不影响 vn.py 启动。

- [x] **P29-T06.3: 接入 DailyReviewService 和启动 bootstrap**
  - 新增：`vnpy_daily_review/service.py`
  - 新增：`vnpy_daily_review/bootstrap.py`
  - 修改：`examples/veighna_trader/run.py`
  - 验收：`configure_daily_review_services(main_engine)` 在 vn.py 启动时把 service 注入 `DailyMarketReviewEngine`。

- [x] **P29-T06.4: PostgreSQL 报告和证据落库**
  - 目标：用 vn.py 现有 `database.*` 和 Peewee `create_tables()` 增加复盘报告、观察计划、证据和审计表。
  - 验收：UI 可加载历史报告，Evidence Pack、明日观察计划和模型审计可查。
  - 状态：已完成第一版。新增 `daily_review_report`、`daily_review_evidence`、`daily_watch_plan`、`daily_watch_plan_item`、`daily_review_model_audit`，并在 `DailyReviewService` 生成报告后落库。

- [x] **P29-T06.5: 新闻/财报/龙虎榜/分时异动增强第一版**
  - 目标：把 P26 新闻公告、P28 财报、龙虎榜和分时异动加入 Evidence Pack。
  - 验收：复盘报告能明确引用新闻公告/财报证据 ID，并能说明哪些数据源缺失。
  - 状态：已完成第一版。provider 会读取 PostgreSQL `news_event`、财报上下文、AKShare 龙虎榜，并从全市场快照生成基础分时异动信号；任一来源失败只记录质量告警。

- [ ] **P29-T06.6: 深度 AI 编排和生产验证**
  - 目标：在 Evidence Pack 之上接入可审计 LLM 多阶段复盘，并做真实数据连续运行验证。
  - 验收：模型审计、token/耗时、失败重试、连续运行结果和次日验证全部落档。

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |
| P29-T01 | 2026-05-11 | 未提交 | 文档已迁入并改写 |
| P29-T02 至 P29-T05 | 2026-05-11 | 未提交 | `uv run --with pytest python -m pytest tests/test_daily_market_review_vnpy_app.py -q`，6 passed |
| P29-T06.1 至 P29-T06.3 | 2026-05-11 | c8d8ccf1 | 迁移核心领域/信号/Evidence Pack，接入 vn.py/AKShare provider 和启动 bootstrap |
| P29-T06.4 至 P29-T06.5 | 2026-05-11 | 未提交 | 报告/证据/观察计划/审计 PostgreSQL 落库；新闻、财报、龙虎榜、基础分时异动进入 Evidence Pack |

## 风险

- 旧 `quantitative-try` 的每日复盘实现是 FastAPI/SQLAlchemy/静态前端，不能原样复制到 vn.py。
- 真实全市场复盘需要大量数据源和调度验证，第一版 UI 可见不等于复盘生产链路已完成。
- 免费公开数据源不稳定，生产环境需要 QMT/券商/商业数据源或至少连续 smoke 验证。
