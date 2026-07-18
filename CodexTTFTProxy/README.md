# Codex TTFT Proxy

本地 Codex HTTP/SSE 中转。上游在规定时间内没有产生文本或工具调用时，代理会取消该连接并重新请求，同时记录当前 Codex 会话标题。

## 要求

- Node.js 24+
- macOS：zsh（系统自带）
- Windows：PowerShell

## 配置

从示例创建本地配置，然后编辑 `proxy-config.json`：

```zsh
cp proxy-config.example.json proxy-config.json
```

`proxy-config.json` 包含 API key，不会被 Git 跟踪。配置格式如下：

```json
{
  "interval": 60,
  "upstream": "https://www.aiwanwu.cc",
  "apiKey": "",
  "ttftTimeoutSeconds": 120,
  "ttftRetries": 4,
  "heartbeatSeconds": 15
}
```

- `interval`：配置热重载周期，单位秒。
- `upstream`：上游 API 的 base URL。
- `apiKey`：非空时覆盖请求原有的 API key；留空时保留请求原有认证信息。
- `ttftTimeoutSeconds`：每轮等待有效输出的时间。
- `ttftRetries`：重试次数；`4` 表示最多请求 5 轮。
- `heartbeatSeconds`：等待期间向 Codex 发送 SSE 注释心跳的间隔。

配置会自动热重载，新请求生效。

## 启动

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:43181/__ttft_proxy/health
```

在 Codex 用户配置 `~/.codex/config.toml` 中，将正在使用的 provider 指向本地代理：

```toml
[model_providers.custom]
base_url = "http://127.0.0.1:43181/"
stream_idle_timeout_ms = 150000
```

保留该 provider 原有的 `name`、`wire_api` 和认证配置。

## 重启

```powershell
$root="$PWD"; Stop-Process -Id (Get-Content "$root\proxy.pid") -Force; Start-Sleep -Milliseconds 300; & "$root\start.ps1"
```

## macOS 登录后自动启动

在项目目录运行一次即可安装并立即启动。它会创建 `launchd` 用户服务，登录 macOS 后会自动启动，进程异常退出时也会自动重启：

```zsh
chmod +x ./autostart.sh
./autostart.sh install
```

查看状态或移除自动启动：

```zsh
./autostart.sh status
./autostart.sh uninstall
```

服务定义位于 `~/Library/LaunchAgents/com.codex.ttft-proxy.plist`，并固定使用当前项目的 `proxy-config.json`。迁移项目目录前，请先执行 `uninstall`，然后在新目录重新安装。

## 日志

`proxy.log` 使用东八区时间，包含当前 UI 会话标题、短线程 ID、尝试轮次和实际输出耗时。代理不记录请求正文和认证头。

```powershell
Get-Content .\proxy.log -Wait
```

## 测试

```powershell
node .\test.mjs
```
