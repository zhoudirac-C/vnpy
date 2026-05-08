# TradingAgents LLM 环境变量配置

TradingAgents 的真实 API key 不写入 vn.py 全局配置文件。全局配置界面可以填写环境变量名，也提供一个真实 key 的安全输入框：

| 字段 | 示例 | 说明 |
| --- | --- | --- |
| `tradingagents.api_key_env_var` | `OPENAI_API_KEY`、`ZHIPU_API_KEY` | Worker 从这个环境变量读取真实 key |
| `tradingagents.api_key` | `sk-...` | 真实 key 的 UI 安全输入框，不保存到 `vt_setting.json` |
| `tradingagents.worker_factory` | `vnpy_tradingagents.tradingagents_factory:build` | 默认 context-only Worker 工厂；等价于环境变量 `TRADINGAGENTS_WORKER_FACTORY` |
| `tradingagents.llm_provider` | `openai`、`zhipu`、`kimi`、`doubao` | LLM provider 名称；UI 会显示国内常用 provider 清单 |
| `tradingagents.model` | `gpt-4o-mini`、`glm-4.7` | Worker 使用的模型 |
| `tradingagents.backend_url` | 空、`https://open.bigmodel.cn/api/coding/paas/v4` | 可选 OpenAI-compatible base URL；留空使用 provider 默认值 |
| `tradingagents.timeout_seconds` | `1800` | 默认超时时间，单位秒；默认 30 分钟 |
| `tradingagents.intraday_thinking_type` | `disabled` | 日内/分时请求 Thinking 开关 |
| `tradingagents.intraday_timeout_seconds` | `360` | 日内/分时请求超时，单位秒 |
| `tradingagents.long_horizon_thinking_type` | `enabled` | 长期研究、组合评级请求 Thinking 开关 |
| `tradingagents.long_horizon_timeout_seconds` | `2700` | 长期研究、组合评级请求超时，单位秒 |
| `tradingagents.replay_thinking_type` | `enabled` | 复盘/回测请求 Thinking 开关 |
| `tradingagents.replay_timeout_seconds` | `2700` | 复盘/回测请求超时，单位秒 |

不要把 `sk-...` 这类真实 key 填到 `tradingagents.api_key_env_var`。该字段只保存变量名。

## 国内常用 provider 和 base_url

`tradingagents.llm_provider` 建议填写下表中的“provider”。部分厂商名称是别名，系统会自动规范化。

| 厂商 | provider | API key 环境变量 | 默认 base_url |
| --- | --- | --- | --- |
| 智谱/BigModel | `glm`，别名 `zhipu`、`bigmodel` | `ZHIPU_API_KEY` | `https://open.bigmodel.cn/api/paas/v4/` |
| 智谱 Coding Plan | `glm`，别名 `zhipu` | `ZHIPU_API_KEY` | `https://open.bigmodel.cn/api/coding/paas/v4` |
| 阿里百炼/通义千问 | `qwen`，别名 `dashscope`、`aliyun` | `DASHSCOPE_API_KEY` | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 月之暗面/Kimi | `kimi`，别名 `moonshot` | `MOONSHOT_API_KEY` | `https://api.moonshot.cn/v1` |
| DeepSeek | `deepseek` | `DEEPSEEK_API_KEY` | `https://api.deepseek.com` |
| 火山方舟/豆包 | `doubao`，别名 `volcengine`、`ark` | `ARK_API_KEY` | `https://ark.cn-beijing.volces.com/api/v3` |
| 腾讯混元 | `hunyuan`，别名 `tencent` | `HUNYUAN_API_KEY` | `https://api.hunyuan.cloud.tencent.com/v1` |
| 百度千帆/文心 | `qianfan`，别名 `baidu`、`wenxin` | `QIANFAN_API_KEY` | `https://qianfan.baidubce.com/v2` |
| MiniMax | `minimax` | `MINIMAX_API_KEY` | `https://api.minimax.io/v1` |
| 讯飞星火 | `spark`，别名 `iflytek`、`xfyun` | `SPARK_API_KEY` | `https://spark-api-open.xf-yun.com/v1` |
| 阶跃星辰 | `stepfun` | `STEPFUN_API_KEY` | `https://api.stepfun.ai/v1` |
| 零一万物 | `yi`，别名 `lingyiwanwu`、`01.ai`、`01ai` | `YI_API_KEY` | `https://api.lingyiwanwu.com/v1` |
| 硅基流动 | `siliconflow` | `SILICONFLOW_API_KEY` | `https://api.siliconflow.cn/v1` |
| 魔搭 ModelScope | `modelscope` | `MODELSCOPE_API_KEY` | `https://api-inference.modelscope.cn/v1` |
| 其他 OpenAI 兼容网关 | `openai_compatible`，别名 `custom`、`openai-compatible` | `OPENAI_API_KEY` 或自定义变量名 | 在 `tradingagents.backend_url` 填供应商地址 |

如果厂商提供了 Coding Plan、海外地域或私有化网关，直接在 `tradingagents.backend_url` 覆盖默认值即可。

## 依赖安装策略

本 fork 默认接入真实 TradingAgents Worker，因此生产环境如果要启用 AI 分析、AI 评级、复盘或回测，需要在部署/构建阶段安装 `tradingagents` 及其 LLM SDK 依赖。当前项目通过 `pyproject.toml` 固定依赖来源，`uv sync`、镜像构建或发布安装时会安装这些依赖。

不要在 vn.py 启动时或 Worker 懒加载时自动联网安装依赖。原因很朴素：生产启动不能依赖外网、不能临时拉未知版本，也不能因为安装耗时让交易进程卡住。现在的设计是：

- 安装发生在部署阶段。
- vn.py 启动不会自动调用大模型。
- TradingAgents Worker 在实际请求到来时才懒加载。
- 缺依赖、缺 key 或配置错误时返回结构化失败，vn.py 原有行情、策略、风控和手工交易链路继续运行。

## Thinking 和超时分层

Worker 会根据 `TradingAgentsWorkerRequest.mode` 自动选择配置：

| 请求类型 | 典型 mode | Thinking | 超时 |
| --- | --- | --- | --- |
| 日内/分时建议 | `intraday_advice`、包含 `intraday` | `tradingagents.intraday_thinking_type=disabled` | `tradingagents.intraday_timeout_seconds=360` |
| 长期研究/组合评级 | `long_horizon`、`long_horizon_batch`、`portfolio`、`research` | `tradingagents.long_horizon_thinking_type=enabled` | `tradingagents.long_horizon_timeout_seconds=2700` |
| 复盘/回测 | 包含 `replay`、`backtest`、`backtesting` | `tradingagents.replay_thinking_type=enabled` | `tradingagents.replay_timeout_seconds=2700` |
| 其他请求 | `report_only` 等 | `tradingagents.thinking_type=auto` | `tradingagents.timeout_seconds=1800` |

日内请求默认关闭 thinking，是为了降低等待时间和结构化输出失败概率；长期研究和复盘默认开启 thinking，是因为这类任务更看重推理质量和审计解释，默认允许 45 分钟。

## 生产链路和回测链路隔离

当前实现把生产和回测按调用边界分开：

- 真实生产策略侧只有 `TradingAgentsSignalStrategy` 和显式混合策略允许消费 AI 信号；传统规则策略默认不继承 AI mixin、不读取 AI 信号。
- AI 策略默认按 `live=True` 检查，只有 `LIVE_ALLOWED` 且 `live_enabled=True` 时才允许把 AI 意图交给真实交易链路。
- `OrderBridge` 默认也按 live scope 处理，未通过 live gate 时只写审计并返回 `order_request=None`。
- 回测、复盘、paper 路径必须显式传 `live=False`，才能消费已落库的 `RatingSignal`、`IntradayAdvice` 或组合意图。
- `BacktestingBridge`、`IntradayReplayEngine`、`PortfolioReplayEngine` 不持有 Gateway/MainEngine，不会触发真实下单。

换成大白话：普通规则策略不吃 AI；独立 AI 策略也默认不能进实盘。回测/复盘可以拿 AI 信号做验证。以后真要让 AI 进入实盘，需要明确打开 `LIVE_ALLOWED + live_enabled`，并通过 live gate、小资金灰度和审计检查。

## vn.py 界面配置方式

在 vn.py 的全局配置界面中：

1. `tradingagents.api_key_env_var` 填环境变量名，例如 `OPENAI_API_KEY` 或 `ZHIPU_API_KEY`。
2. `tradingagents.api_key <secret>` 填真实 key。该字段是密码输入框，不会写入 `vt_setting.json`。
3. 不勾选“保存到系统钥匙串”时，key 只写入当前 vn.py 进程环境变量，重启后需要重新配置或通过系统环境变量注入。
4. 勾选“保存到系统钥匙串”且安装可选依赖 `keyring` 时，key 会写入 macOS Keychain、Windows Credential Manager 或 Linux keyring 后端。

`tradingagents.worker_factory` 默认已经填好：

```text
vnpy_tradingagents.tradingagents_factory:build
```

这和设置环境变量等价：

```bash
export TRADINGAGENTS_WORKER_FACTORY="vnpy_tradingagents.tradingagents_factory:build"
```

如果从 vn.py UI 启动，保留默认 `tradingagents.worker_factory` 即可；如果从 systemd、Docker 或 CI 启动 vn.py 进程，也可以用 `TRADINGAGENTS_WORKER_FACTORY` 注入同一个值。

安装可选钥匙串支持：

```bash
uv pip install "vnpy[llm-secrets]"
```

生产环境仍建议通过系统环境变量、容器 Secret 或云 Secret Manager 注入；UI 输入更适合本机开发、联调和临时验证。

## BigModel/智谱配置

如果使用智谱开放平台通用 API：

```text
tradingagents.llm_provider = zhipu
tradingagents.api_key_env_var = ZHIPU_API_KEY
tradingagents.model = glm-4.7
tradingagents.backend_url =
```

如果使用 GLM Coding Plan，需要使用 Coding 专用端点：

```text
tradingagents.llm_provider = zhipu
tradingagents.api_key_env_var = ZHIPU_API_KEY
tradingagents.model = glm-4.7
tradingagents.backend_url = https://open.bigmodel.cn/api/coding/paas/v4
```

智谱官方文档说明，通用 API 端点是 `https://open.bigmodel.cn/api/paas/v4`，Coding Plan 使用 `https://open.bigmodel.cn/api/coding/paas/v4`。如果你的 key 是从 Coding Plan 获取的，优先按第二组配置验证。

## macOS/Linux 临时配置

```bash
export OPENAI_API_KEY="sk-..."
# 或
export ZHIPU_API_KEY="..."
```

只对当前终端有效。若从这个终端启动 vn.py，TradingAgents Worker 可以读取该变量。

## macOS/Linux zsh 持久配置

```bash
echo 'export OPENAI_API_KEY="sk-..."' >> ~/.zshrc
# 或
echo 'export ZHIPU_API_KEY="..."' >> ~/.zshrc
source ~/.zshrc
```

重新打开终端后依然生效。

## macOS GUI 程序环境变量

如果 vn.py 是从桌面、Dock 或 IDE GUI 启动，普通 `~/.zshrc` 不一定会被读取。可以使用：

```bash
launchctl setenv OPENAI_API_KEY "sk-..."
# 或
launchctl setenv ZHIPU_API_KEY "..."
```

设置后重新启动 GUI 程序。

## Windows PowerShell 临时配置

```powershell
$env:OPENAI_API_KEY="sk-..."
# 或
$env:ZHIPU_API_KEY="..."
```

只对当前 PowerShell 窗口有效。

## Windows 用户级持久配置

```powershell
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "sk-...", "User")
# 或
[Environment]::SetEnvironmentVariable("ZHIPU_API_KEY", "...", "User")
```

设置后重新打开终端、IDE 或 vn.py。

## 容器和云服务

```bash
docker run -e OPENAI_API_KEY="sk-..." ...
# 或
docker run -e ZHIPU_API_KEY="..." ...
```

生产环境建议使用容器 Secret、Kubernetes Secret、云厂商 Secret Manager 或 CI/CD Secret 注入，不要把真实 key 写进代码、文档、日志、数据库或 `vt_setting.json`。

## 未配置 key 时的降级行为

未配置 API key 时，TradingAgents Worker 不调用大模型，返回 `configuration_error` 或 `unavailable`。系统不生成 AI 评级和 AI 交易意图，vn.py 原有行情、策略、风控、下单和手工交易链路继续运行。
