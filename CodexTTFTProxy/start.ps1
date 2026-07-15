$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$health = 'http://127.0.0.1:43181/__ttft_proxy/health'

$running = $false
try {
    Invoke-RestMethod -Uri $health -TimeoutSec 2 | Out-Null
    $running = $true
} catch {}

if (-not $running) {
    $node = (Get-Command node -ErrorAction Stop).Source
    $stdout = Join-Path $root 'proxy.log'
    $stderr = Join-Path $root 'proxy.error.log'
    $process = Start-Process -FilePath $node -ArgumentList (Join-Path $root 'proxy.mjs') -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $process.Id | Set-Content -LiteralPath (Join-Path $root 'proxy.pid')

    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 250
        try {
            Invoke-RestMethod -Uri $health -TimeoutSec 2 | Out-Null
            $running = $true
            break
        } catch {}
    }

    if (-not $running) {
        throw "TTFT proxy failed to start. See $stderr"
    }
}
