# P31 七轨布林线扫描与 TradingAgents 联动验证结果

验证日期：2026-05-12

验证对象：

- 七轨布林线日线指标与信号规则
- CTA 日线策略与轻量回测校验
- 全市场日线扫描服务
- 扫描结果落库
- 午盘预览/收盘正式调度器
- TradingAgents Engine/UI 联动
- 七轨扫描结果注入 TradingAgents 手动分析上下文

固定口径：

- 全程只使用 `Interval.DAILY` 日线语义。
- 扫描行情获取路径限定为 vn.py 数据路径：优先 `database.load_bar_data`，再通过 `get_datafeed().query_bar_history` 调用 router datafeed。
- Scanner 不直接绑定 AKShare。
- 扫描落库只保存 scan run/result，不重复保存原始 K 线行情。

## 代码级验证

命令：

```bash
uv run --with pytest python -m pytest tests/test_seven_boll_indicator.py tests/test_seven_boll_signals.py tests/test_seven_boll_cta_strategy.py tests/test_seven_boll_backtest_strategy.py tests/test_seven_boll_scanner.py tests/test_seven_boll_storage.py tests/test_seven_boll_scheduler.py tests/test_seven_boll_engine_integration.py tests/test_seven_boll_ui.py tests/test_seven_boll_tradingagents_context.py -q
```

结果：

```text
31 passed, 1 warning in 1.24s
```

警告来自 peewee `autorollback` deprecation，不影响 P31 功能判断。

覆盖点：

| 场景 | 验证方式 | 结果 |
| --- | --- | --- |
| 指标单测 | 合成日线 bars 覆盖趋势、震荡、极端位置和收口样本 | 通过 |
| 信号单测 | 趋势回踩、收口突破、均值回归、过热减仓、趋势退出 | 通过 |
| CTA 策略单测 | 日线 `BarData` 驱动策略信号和目标仓位 | 通过 |
| 回测校验 | `BacktestingEngine` 跑三类日线场景 | 通过 |
| 手动扫描 | fake history provider 驱动 `SevenBollScanService.scan()` | 通过 |
| 扫描行情路径 | 测试约束 scanner 使用 vn.py database/datafeed，不直接依赖 AKShare | 通过 |
| 扫描落库 | `SevenBollScanRepository` 只落 scan run/result | 通过 |
| 午盘预览定时 | `11:35` 触发 `scan_type=preview` | 通过 |
| 收盘正式定时 | `15:05` 触发 `scan_type=official` | 通过 |
| 单点分析 | Engine 从 scan result 触发 `mode=seven_boll_scan_analysis` | 通过 |
| 批量分析 | Engine 对候选列表逐个生成分析 run id | 通过 |
| UI 冒烟 | 七轨 Tab、候选表、状态列、报告入口和配置项静态约束 | 通过 |
| TradingAgents 上下文 | `seven_boll_scan` 与日线技术面约束注入 manual analysis context | 通过 |

## 生产级限制

本次是代码级闭环验证，不是生产级 SLA 验证：

- 没有连接真实交易时段的全市场数据库做完整 A 股扫描耗时统计。
- 没有在真实 vn.py GUI 会话中等待 11:35 和 15:05 自然触发。
- 没有调用真实大模型批量生成报告并评估成本、时延、失败重试率。
- 没有把扫描结果接入自动下单；P31 第一阶段也不允许自动下单。

后续若进入生产灰度，至少还需要连续交易日验证：数据覆盖率、扫描耗时、router datafeed 限流、TradingAgents 成本、失败重试、UI 长任务体验和报告质量抽样。
