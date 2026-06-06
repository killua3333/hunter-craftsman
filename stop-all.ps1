# ============================================================
#  Hunter + Craftsman 一键停止脚本
#  关闭占用 8791 / 8800 / 5173 端口的进程
# ============================================================

Write-Host "正在停止 Hunter + Craftsman 服务..." -ForegroundColor Cyan

foreach ($port in 8791, 8800, 5173) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conns) {
        foreach ($conn in $conns) {
            $procId = $conn.OwningProcess
            try {
                Stop-Process -Id $procId -Force -ErrorAction Stop
                Write-Host "  已停止端口 $port (PID $procId)" -ForegroundColor Green
            } catch {
                Write-Host "  停止端口 $port 失败: $_" -ForegroundColor Red
            }
        }
    } else {
        Write-Host "  端口 $port 未在运行" -ForegroundColor Yellow
    }
}

Write-Host "完成。" -ForegroundColor Cyan
