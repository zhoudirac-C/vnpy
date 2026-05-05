# P22 UI 可用性修复任务

目标：修复当前 vn.py 桌面端联调中暴露的低成本高影响问题，让用户能更顺畅地配置数据源、LLM、回测和交易面板。

## 任务清单

- [ ] **P22-T01: 交易面板空交易所错误提示**
  - 目标：当交易所下拉为空或用户未选择交易所时，不抛 Python `ValueError` 弹窗，改为状态栏/日志提示。
  - 验收：输入代码但交易所为空时，不触发异常弹窗。

- [ ] **P22-T02: AKShare 数据源配置说明**
  - 目标：在文档和 UI help 中说明 `datafeed.name=router`、`router.providers=akshare`、`router.local_path` 的关系。
  - 验收：用户知道 AKShare 是历史 Datafeed，不是实时 Gateway。

- [ ] **P22-T03: 回测入口说明**
  - 目标：说明 CTA 策略和 CTA 回测 App 已自动加载，以及如何进入“功能 -> CTA回测”。
  - 验收：文档包含最小回测操作路径。

- [ ] **P22-T04: TradingAgents provider/base_url UI 清单一致性**
  - 目标：UI 中的 provider 清单和 `tradingagents_llm_env.md` 保持一致。
  - 验收：新增国内 provider 时有测试覆盖说明文本。

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |
| P22-T01 | 未完成 | 未提交 | 未运行 |
| P22-T02 | 未完成 | 未提交 | 未运行 |
| P22-T03 | 未完成 | 未提交 | 未运行 |
| P22-T04 | 未完成 | 未提交 | 未运行 |
