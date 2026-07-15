# Codex TTFT Proxy

Windows 下的本地 Codex HTTP/SSE 中转。上游在规定时间内没有产生文本或工具调用时，代理会取消该连接并重新请求，同时记录当前 Codex 会话标题。

## 要求

- Node.js 24+
- PowerShell

## 配置

编辑 `proxy-config.json`：

```json
{
  "interval": 60,
  "upstream": "https://www.aiwanwu.cc",
  "ttftTimeoutSeconds": 120,
  "ttftRetries": 4,
  "heartbeatSeconds": 15
}
```

- `interval`：配置热重载周期，单位秒。
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

## 日志

`proxy.log` 使用东八区时间，包含当前 UI 会话标题、短线程 ID、尝试轮次和实际输出耗时。代理不记录请求正文和认证头。

```powershell
Get-Content .\proxy.log -Wait
```

## 测试

```powershell
node .\test.mjs
```
