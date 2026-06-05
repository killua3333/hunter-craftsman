# ============================================================
#  Hunter-Craftsman Windows Task Scheduler 注册脚本
#  在"用户登录时"自动启动调度器（循环运行，每小时发一版新 app）。
# ============================================================
#  用法（以管理员身份运行 PowerShell）:
#   .\install_task.ps1                    安装任务
#   .\install_task.ps1 -Uninstall         卸载任务
#   .\install_task.ps1 -IntervalMinutes 60 自定义间隔
# ============================================================

param(
    [switch]$Uninstall,
    [int]$IntervalMinutes = 60
)

$TaskName = "HunterCraftsman_AutoPilot"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BatchFile = Join-Path $ScriptDir "run_autopilot.bat"

if ($Uninstall) {
    Write-Host "卸载计划任务: $TaskName" -ForegroundColor Yellow
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
        Write-Host "[成功] 任务已卸载。" -ForegroundColor Green
    }
    catch {
        if ($_.Exception.Message -match "不存在") {
            Write-Host "[信息] 任务不存在，无需卸载。" -ForegroundColor Cyan
        }
        else {
            Write-Host "[错误] 卸载失败: $_" -ForegroundColor Red
            exit 1
        }
    }
    exit 0
}

# 安装
Write-Host "=== Hunter-Craftsman 任务计划程序安装 ===" -ForegroundColor Green
Write-Host "任务名称: $TaskName"
Write-Host "批处理路径: $BatchFile"
Write-Host "触发条件: 用户登录时触发 + 每 $IntervalMinutes 分钟重复"
Write-Host ""

if (-not (Test-Path $BatchFile)) {
    Write-Host "[错误] 未找到 $BatchFile，请确认脚本路径正确。" -ForegroundColor Red
    exit 1
}

# 先删除旧任务（如果存在）
try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
}
catch {}

# 创建触发器：登录时触发，之后每 N 分钟重复一次
$Trigger = New-ScheduledTaskTrigger -AtLogOn -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) -RepetitionDuration ([TimeSpan]::MaxValue)

# 创建操作
$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$BatchFile`" --interval $IntervalMinutes"

# 设置：允许任务在电池模式下运行，隐藏窗口
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew

# 注册任务
try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Trigger $Trigger `
        -Action $Action `
        -Settings $Settings `
        -Description "Hunter-Craftsman 自动调度：每 $IntervalMinutes 分钟触发 Agent A 发现 + Agent B 生成 + Agent C 发布" `
        -TaskPath "\" `
        -Force `
        -ErrorAction Stop
    Write-Host "[成功] 任务已注册。" -ForegroundColor Green
    Write-Host ""
    Write-Host "--- 使用提示 ---" -ForegroundColor Cyan
    Write-Host "- 手动触发一次:   schtasks /run /tn `"$TaskName`""
    Write-Host "- 查看任务详情:   schtasks /query /tn `"$TaskName`" /v /fo LIST"
    Write-Host "- 查看运行历史:   Get-ScheduledTaskInfo -TaskName `"$TaskName`""
    Write-Host "- 卸载任务:       .\install_task.ps1 -Uninstall"
    Write-Host ""
    Write-Host "任务会在用户下次登录时自动启动。" -ForegroundColor Cyan
}
catch {
    Write-Host "[错误] 注册失败: $_" -ForegroundColor Red
    Write-Host "请确保以管理员权限运行此脚本。" -ForegroundColor Yellow
    exit 1
}
