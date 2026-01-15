# PowerShell script to start live trading engine
# Usage: .\start_live.ps1 [--no-trading|--test-order]

param(
    [switch]$NoTrading,
    [switch]$TestOrder,
    [string]$ExecutionBroker = "HAMMER",
    [string]$IBKRAccount = "",
    [string]$HammerAccount = "ALARIC:TOPI002240A7"
)

Write-Host "🚀 Starting Live Trading Engine..." -ForegroundColor Green
Write-Host ""

# Build command
$cmd = "python main.py live --execution-broker $ExecutionBroker"

if ($ExecutionBroker -eq "IBKR") {
    if ($IBKRAccount -eq "") {
        Write-Host "❌ Error: --ibkr-account required when using IBKR" -ForegroundColor Red
        Write-Host "Usage: .\start_live.ps1 -ExecutionBroker IBKR -IBKRAccount DU123456" -ForegroundColor Yellow
        exit 1
    }
    $cmd += " --ibkr-account $IBKRAccount"
} else {
    $cmd += " --hammer-account $HammerAccount"
}

if ($NoTrading) {
    $cmd += " --no-trading"
    Write-Host "📊 Mode: Data subscribe only (no orders)" -ForegroundColor Cyan
} elseif ($TestOrder) {
    $cmd += " --test-order"
    Write-Host "🧪 Mode: Test order (dry-run)" -ForegroundColor Yellow
} else {
    Write-Host "🚀 Mode: LIVE TRADING (orders enabled)" -ForegroundColor Red
    Write-Host "⚠️  WARNING: Real orders will be sent!" -ForegroundColor Red
    $confirm = Read-Host "Continue? (yes/no)"
    if ($confirm -ne "yes") {
        Write-Host "Cancelled." -ForegroundColor Yellow
        exit 0
    }
}

Write-Host ""
Write-Host "Executing: $cmd" -ForegroundColor Gray
Write-Host ""

# Execute
Invoke-Expression $cmd








