# TradingAgents 线上 Thinking 冒烟测试

日期：2026-05-05

## 测试目标

验证 vn.py 内嵌 TradingAgents Worker 在真实 BigModel/GLM-4.7 API 下的可用性，并对比：

- `thinking=disabled` 的完整 TradingAgents 链路耗时。
- `thinking=enabled` 的完整 TradingAgents 链路耗时。
- 单次 LLM 调用耗时和 TradingAgents 多角色链路耗时的差异。

本次测试不记录、不输出 API key。

## 测试环境

- 分支：`feature/akshare-tradingagents-architecture`
- LLM provider：UI 填 `zhipu`，运行时规范化为 upstream TradingAgents 的 `glm`
- 模型：`glm-4.7`
- API key 来源：vn.py UI 安全输入 + keyring/env 解析
- Worker factory：`vnpy_tradingagents.tradingagents_factory:build`
- Worker 形态：vn.py 进程内懒加载，不启动独立 TradingAgents 服务
- Context：本地构造 `600519.SSE` market bars + indicators 快照
- 单次 LLM 输出上限：`tradingagents.max_completion_tokens=1024`

## 验证结果

| 用例 | Thinking | 超时上限 | 结果 | 耗时 | 输出 |
|---|---:|---:|---|---:|---|
| 单次 BigModel LLM | disabled | 120s | 通过 | 1.43s | `OK` |
| 单次 BigModel LLM | enabled | 120s | 通过 | 11.94s | `OK` |
| 完整 TradingAgents 链路 | disabled | 900s | 通过 | 230.58s | `Buy/buy` |
| 完整 TradingAgents 链路 | enabled | 1800s | 通过 | 1480.67s | `Hold/hold` |

## 关键观察

1. `thinking=disabled` 能稳定跑完整链路，完整 TradingAgents 多角色执行约 3.8 分钟。
2. `thinking=enabled` 能跑通，但耗时约 24.7 分钟，不适合作为日内分时路径默认配置。
3. `thinking=enabled` 期间出现 Research Manager、Trader、Portfolio Manager 结构化输出失败并降级自由文本重试；这会增加耗时和不确定性。
4. GLM-4.7 官方文档说明 GLM-4.7 默认开启 Thinking，且 Thinking + Tool Calling 需要显式保留 reasoning content。当前 upstream TradingAgents 对 GLM 没有 DeepSeek 那样的 reasoning_content 往返适配，因此生产默认应保持 `auto`，由我们在 GLM-4.7 下转为 `disabled`。
5. Artificial Analysis 的公开基准显示 GLM-4.7 reasoning 模型在 10k 输入 token 下，不同 provider 的首答延迟和输出速度差异很大；TradingAgents 不是单次调用，而是多个 agent 串行和工具轮转，所以完整耗时会远大于单次模型延迟。

## 资料来源

- 智谱 Thinking 模式文档：GLM-5.1/GLM-5/GLM-4.7 默认开启 Thinking，可用 `thinking.type=disabled` 关闭。
  https://docs.bigmodel.cn/cn/guide/capabilities/thinking-mode
- 智谱 OpenAI API 兼容文档：支持 OpenAI SDK 兼容调用、thinking 参数、函数调用、超时与重试建议。
  https://docs.bigmodel.cn/cn/guide/develop/openai/introduction
- TradingAgents 官方架构页：包含 analyst、researcher、trader、risk manager 等多角色流程。
  https://tradingagents-ai.github.io/
- Artificial Analysis GLM-4.7 benchmark：用于参考首 token 延迟、输出速度、端到端响应时间口径。
  https://artificialanalysis.ai/models/glm-4-7/providers

## 生产建议

- 日内/分时：默认 `tradingagents.thinking_type=auto`，GLM-4.7 运行时按 `disabled` 处理；建议超时 300-600 秒，输出上限 1024-1536。
- 长周期研究：可允许用户显式改为 `enabled`，但应设置独立超时、成本预算、审计记录，并提示耗时可能达到 20-30 分钟。
- UI 已补充 provider 正确名称清单：`openai`、`anthropic`、`google`、`azure`、`xai`、`deepseek`、`qwen`、`glm`、`openrouter`、`ollama`，并保留别名 `zhipu/bigmodel -> glm`、`dashscope -> qwen`。
