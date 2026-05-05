# P21 股票 Gateway 和仿真验证任务

目标：验证股票交易相关链路如何接入 vn.py Gateway、仿真 Gateway 或 PaperAccount，确保 AI 只进入建议/审计/风控边界，不绕过 vn.py 原生下单链路。

## 任务清单

- [x] **P21-T01: 股票 Gateway 选择清单**
  - 目标：列出当前股票交易候选插件：QMT/XT、XTP、TORA、仿真/Paper，并说明安装、账号、市场限制。
  - 验收：文档能指导用户选择“先仿真、后实盘”的路径。

- [x] **P21-T02: 仿真 Gateway AI 信号验证**
  - 目标：在无真实券商账号条件下，用仿真或 paper profile 验证 AI 信号只能被策略读取，不能直接触碰 Gateway。
  - 验收：审计记录包含 gateway profile、account mode、AI 开关状态。

- [x] **P21-T03: live gate 最小实盘准入检查**
  - 目标：把小资金前必须满足的 simulation 稳定天数、最大回撤、失败率、手工接管能力固化成检查。
  - 验收：未满足时 `live_enabled` 不能打开。

- [ ] **P21-T04: QMT/XT 插件联调记录**
  - 前置：开通 QMT/XT 账号和对应 vn.py 插件。
  - 目标：验证行情订阅、合约缓存、手工下单、策略下单、AI 只读信号。
  - 验收：联调结果落档，失败项标为 Blocked 或 Failed。

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |
| P21-T01 | 2026-05-05 | 未提交 | 文档检查 |
| P21-T02 | 2026-05-05 | 未提交 | `uv run --with pytest pytest tests/test_tradingagents_gray_release.py::test_paper_bridge_enables_only_simulation_and_writes_trade_feedback -q` |
| P21-T03 | 2026-05-05 | 未提交 | `uv run --with pytest pytest tests/test_tradingagents_gray_release.py::test_live_gate_blocks_high_failure_rate_and_missing_manual_takeover -q` |
| P21-T04 | Blocked | 未提交 | 等待真实 QMT/XT 环境 |

## P21-T01 股票 Gateway 选择清单

| 路径 | vn.py 角色 | 适合阶段 | 需要准备 | 备注 |
| --- | --- | --- | --- | --- |
| CTA Backtesting | BacktestingEngine/App | 本地验证、策略回测 | 历史 K 线、策略参数 | 不连接券商，不代表实盘可用；P19 已跑通 AI 信号回测闭环 |
| Paper/Simulation | PaperAccount 或仿真 Gateway profile | 连续演练、灰度前验证 | 仿真账户、回放数据、审计导出 | AI 只能在 `PAPER_ONLY` 或 simulation profile 下消费信号 |
| QMT/XT | vn.py Gateway/Datafeed 插件 | A 股实盘候选 | QMT 账号、券商权限、`vnpy_xt` 等插件 | 实时行情、合约、委托、成交都走 vn.py 插件；本 fork 不直连 `xtquant` |
| XTP | vn.py Gateway 插件 | A 股实盘候选 | XTP 账号、柜台权限、插件安装 | 适合已有 XTP 环境的股票/ETF 交易 |
| TORA | vn.py Gateway 插件 | A 股实盘候选 | TORA 账号、柜台权限、插件安装 | 适合机构或券商柜台环境 |

推荐顺序：

1. 本地 P19 回测闭环。
2. Paper/Simulation 连续运行，确认 `decision_audit`、feedback、heartbeat、手工接管。
3. QMT/XT、XTP 或 TORA 真实 Gateway 联调，只先验证行情订阅和手工交易。
4. LiveGate 全部 ready 后，再考虑小资金 `live_allowed`。

## P21-T02 仿真验证补充

`PaperAccountBridge` 现在会在 simulated trade/performance feedback payload 中记录：

- `gateway_name`
- `account_mode`
- `ai_enabled`

这让后续审计能回答：某次模拟成交来自哪个 Gateway profile，当时 AI 开关是否启用。它仍不持有真实 `Gateway` 或 `MainEngine`。

## P21-T03 LiveGate 补充

`LiveGate` 当前最小准入条件：

- `runtime.can_use_signal(live=True)` 已显式打开。
- simulation stable days 达到下限。
- max drawdown 不超过上限。
- audit completeness 达到下限。
- failure rate 不超过上限。
- 手工接管能力 ready。

缺任一项都不能进入小资金 AI live mode。
