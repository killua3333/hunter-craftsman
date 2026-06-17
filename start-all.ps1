# ============================================================
#  Hunter + Craftsman 一键启动脚本
#  启动三个常驻服务：Craftsman(8791) + Gateway(8800) + UI(5173)
#  自动创建虚拟环境并安装依赖
# ============================================================

$root = $PSScriptRoot

$craftsmanVenv = "$root\craftsman\.venv"
$craftsmanPython = "$craftsmanVenv\Scripts\python.exe"

function Test-PortInUse($port) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $conn
}

function Ensure-Venv {
    param($venvPath, $requirementsPath, $label)
    if (-not (Test-Path $venvPath)) {
        Write-Host "  创建 $label 虚拟环境..." -ForegroundColor Yellow
        python -m venv $venvPath
    }
    $pip = "$venvPath\Scripts\pip.exe"
    & $pip install -q -r $requirementsPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  $label 依赖安装失败！" -ForegroundColor Red
        exit 1
    }
    Write-Host "  $label 虚拟环境就绪" -ForegroundColor Green
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Hunter + Craftsman 启动中..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ---------- 准备虚拟环境 ----------
Write-Host "[0] 准备虚拟环境..." -ForegroundColor Cyan
Ensure-Venv -venvPath $craftsmanVenv -requirementsPath "$root\craftsman\requirements.txt" -label "Craftsman"
Ensure-Venv -venvPath $craftsmanVenv -requirementsPath "$root\dashboard\gateway\requirements.txt" -label "Gateway"
Write-Host ""

# ---------- 1. Craftsman 核心服务 (8791) ----------
if (Test-PortInUse 8791) {
    Write-Host "[1/3] Craftsman (8791) 已在运行，跳过" -ForegroundColor Yellow
} else {
    Write-Host "[1/3] 启动 Craftsman 核心服务 (8791)..." -ForegroundColor Green
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\craftsman'; & '$craftsmanPython' -m craftsman.cli serve"
    Start-Sleep -Seconds 4
}

# ---------- 2. Dashboard Gateway (8800) ----------
if (Test-PortInUse 8800) {
    Write-Host "[2/3] Gateway (8800) 已在运行，跳过" -ForegroundColor Yellow
} else {
    Write-Host "[2/3] 启动 Dashboard Gateway (8800)..." -ForegroundColor Green
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\dashboard\gateway'; `$env:PORT=8800; & '$craftsmanPython' main.py"
    Start-Sleep -Seconds 3
}

# ---------- 3. 前端 UI (5173) ----------
if (Test-PortInUse 5173) {
    Write-Host "[3/3] 前端 UI (5173) 已在运行，跳过" -ForegroundColor Yellow
} else {
    Write-Host "[3/3] 启动前端 UI (5173)..." -ForegroundColor Green
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\dashboard\ui'; npm run dev"
    Start-Sleep -Seconds 5
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " 启动完成！" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host " 前端面板:   http://localhost:5173" -ForegroundColor White
Write-Host " Gateway:    http://127.0.0.1:8800" -ForegroundColor White
Write-Host " Craftsman:  http://127.0.0.1:8791/health" -ForegroundColor White
Write-Host ""
Write-Host " 跑流水线（另开终端）:" -ForegroundColor White
Write-Host "   cd $root\hunter" -ForegroundColor Gray
Write-Host "   .\.venv\Scripts\Activate.ps1" -ForegroundColor Gray
Write-Host '   hunter run "做一个离线番茄钟" --timeout 1800' -ForegroundColor Gray
Write-Host ""

Start-Sleep -Seconds 2
Start-Process "http://localhost:5173"
