# TradingAgents LLM 环境变量配置

TradingAgents 的真实 API key 不写入 vn.py 全局配置文件。全局配置界面可以填写环境变量名，也提供一个真实 key 的安全输入框：

| 字段 | 示例 | 说明 |
| --- | --- | --- |
| `tradingagents.api_key_env_var` | `OPENAI_API_KEY` | Worker 从这个环境变量读取真实 key |
| `tradingagents.api_key` | `sk-...` | 真实 key 的 UI 安全输入框，不保存到 `vt_setting.json` |
| `tradingagents.worker_factory` | `vnpy_tradingagents.tradingagents_factory:build` | 默认 context-only Worker 工厂；等价于环境变量 `TRADINGAGENTS_WORKER_FACTORY` |
| `tradingagents.llm_provider` | `openai` | LLM provider 名称 |
| `tradingagents.model` | `gpt-4o-mini` | Worker 使用的模型 |

不要把 `sk-...` 这类真实 key 填到 `tradingagents.api_key_env_var`。该字段只保存变量名。

## vn.py 界面配置方式

在 vn.py 的全局配置界面中：

1. `tradingagents.api_key_env_var` 填环境变量名，例如 `OPENAI_API_KEY`。
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

## macOS/Linux 临时配置

```bash
export OPENAI_API_KEY="sk-..."
```

只对当前终端有效。若从这个终端启动 vn.py，TradingAgents Worker 可以读取该变量。

## macOS/Linux zsh 持久配置

```bash
echo 'export OPENAI_API_KEY="sk-..."' >> ~/.zshrc
source ~/.zshrc
```

重新打开终端后依然生效。

## macOS GUI 程序环境变量

如果 vn.py 是从桌面、Dock 或 IDE GUI 启动，普通 `~/.zshrc` 不一定会被读取。可以使用：

```bash
launchctl setenv OPENAI_API_KEY "sk-..."
```

设置后重新启动 GUI 程序。

## Windows PowerShell 临时配置

```powershell
$env:OPENAI_API_KEY="sk-..."
```

只对当前 PowerShell 窗口有效。

## Windows 用户级持久配置

```powershell
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "sk-...", "User")
```

设置后重新打开终端、IDE 或 vn.py。

## 容器和云服务

```bash
docker run -e OPENAI_API_KEY="sk-..." ...
```

生产环境建议使用容器 Secret、Kubernetes Secret、云厂商 Secret Manager 或 CI/CD Secret 注入，不要把真实 key 写进代码、文档、日志、数据库或 `vt_setting.json`。

## 未配置 key 时的降级行为

未配置 API key 时，TradingAgents Worker 不调用大模型，返回 `configuration_error` 或 `unavailable`。系统不生成 AI 评级和 AI 交易意图，vn.py 原有行情、策略、风控、下单和手工交易链路继续运行。
