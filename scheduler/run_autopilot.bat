@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ============================================================
REM  Hunter-Craftsman 一键自动调度启动脚本
REM  用法:
REM    run_autopilot.bat                   默认间隔 30 分钟，循环运行
REM    run_autopilot.bat --once            只跑一轮
REM    run_autopilot.bat --interval 60     每 60 分钟一轮
REM    run_autopilot.bat --no-publish      只发现+生成，不上架
REM ============================================================

REM 确定项目根目录（当前脚本所在目录的父目录）
set "PROJECT_ROOT=%~dp0.."
pushd "%PROJECT_ROOT%"

echo.
echo ============================================================
echo  Hunter-Craftsman AutoPilot Scheduler
echo ============================================================
echo  项目目录: %CD%
echo  间隔: %INTERVAL_MINUTES%分钟 (可通过命令行参数覆盖)
echo.

REM 读取 .env 环境变量
if exist "hunter\.env" (
    echo [env] 加载 hunter\.env
    for /f "tokens=*" %%a in (hunter\.env) do (
        set "line=%%a"
        if not "!line!"=="" if not "!line:~0,1!"=="#" set "%%a"
    )
)
if exist "craftsman\.env" (
    echo [env] 加载 craftsman\.env
    for /f "tokens=*" %%a in (craftsman\.env) do (
        set "line=%%a"
        if not "!line!"=="" if not "!line:~0,1!"=="#" set "%%a"
    )
)

REM 检测 Python 环境
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请确保已安装并加入 PATH。
    pause
    exit /b 1
)

echo [python] %PYTHON_EXE%

REM 运行调度器，把所有参数透传过去
echo.
echo [启动] 开始调度循环...
echo ============================================================
echo.

python "scheduler\autopilot_loop.py" %*

echo.
echo [结束] 调度器已退出。
popd
pause
