@echo off
REM ============================================================
REM  Google Play 发布环境准备脚本
REM  将此脚本放在 craftsman 目录下运行
REM ============================================================

echo ========================================
echo  Google Play 发布密钥生成工具
echo ========================================
echo.

REM ---------- 1. Keystore 生成 ----------
echo [1/2] 生成 Android 签名密钥 (release.jks)...
echo.

set KEYSTORE_FILE=secrets\release.jks
set KEY_ALIAS=release
set KEYSTORE_PASS=
set KEY_PASS=

REM 如果 keystore 已存在，询问是否覆盖
if exist "%KEYSTORE_FILE%" (
    echo 密钥文件 %KEYSTORE_FILE% 已存在！
    set /p OVERWRITE="覆盖? (y/N): "
    if /i not "%OVERWRITE%"=="y" goto skip_keystore
    del "%KEYSTORE_FILE%"
)

echo 请输入 keystore 密码（至少 6 位）：
set /p KEYSTORE_PASS="密码: "
echo 请再次输入 keystore 密码确认：
set /p KEYSTORE_PASS2="确认: "

if not "%KEYSTORE_PASS%"=="%KEYSTORE_PASS2%" (
    echo 密码不匹配！请重试。
    exit /b 1
)

set KEY_PASS=%KEYSTORE_PASS%

echo.
echo 正在生成密钥...
keytool -genkeypair -v ^
  -storetype JKS ^
  -keyalg RSA ^
  -keysize 2048 ^
  -validity 10000 ^
  -alias %KEY_ALIAS% ^
  -keystore %KEYSTORE_FILE% ^
  -storepass %KEYSTORE_PASS% ^
  -keypass %KEY_PASS% ^
  -dname "CN=Hunter Craftsman, OU=Dev, O=HunterCraftsman, L=Beijing, ST=Beijing, C=CN"

if %ERRORLEVEL% NEQ 0 (
    echo 密钥生成失败！请确认已安装 JDK（需要 keytool 命令）。
    echo 下载 JDK: https://adoptium.net/
    exit /b 1
)

echo.
echo 密钥已生成: %KEYSTORE_FILE%
echo.

:skip_keystore

REM ---------- 2. 输出 .env 配置模板 ----------
echo [2/2] 生成 .env 配置模板...
echo.

set ENV_FILE=..env.google_play.txt

echo # ====== 将以下内容添加到 craftsman\.env 末尾 ====== > "%ENV_FILE%"
echo. >> "%ENV_FILE%"
echo # 关闭干跑模式 >> "%ENV_FILE%"
echo PUBLISHER_DRY_RUN=false >> "%ENV_FILE%"
echo. >> "%ENV_FILE%"
echo # Android 签名密钥 >> "%ENV_FILE%"
echo ANDROID_KEYSTORE_PATH=./secrets/release.jks >> "%ENV_FILE%"
echo ANDROID_KEYSTORE_PASSWORD=YOUR_PASSWORD_HERE >> "%ENV_FILE%"
echo ANDROID_KEY_ALIAS=release >> "%ENV_FILE%"
echo ANDROID_KEY_PASSWORD=YOUR_PASSWORD_HERE >> "%ENV_FILE%"
echo. >> "%ENV_FILE%"
echo # Google Play API 服务账号（二选一） >> "%ENV_FILE%"
echo GOOGLE_PLAY_SERVICE_ACCOUNT_FILE=./secrets/play-sa.json >> "%ENV_FILE%"
echo # 或 >> "%ENV_FILE%"
echo # GOOGLE_PLAY_SERVICE_ACCOUNT_JSON={"type":"service_account",...} >> "%ENV_FILE%"
echo. >> "%ENV_FILE%"
echo # 可选：固定包名 >> "%ENV_FILE%"
echo # GOOGLE_PLAY_PACKAGE_NAME=com.yourbrand.appname >> "%ENV_FILE%"

echo 配置模板已保存到: %ENV_FILE%
echo.

echo ========================================
echo  准备完成！
echo ========================================
echo.
echo 接下来需要你做（人工操作）：
echo.
echo   A. 在 Google Play Console 创建 App
echo      https://play.google.com/console
echo      记下包名（如 com.yourbrand.myapp）
echo.
echo   B. 创建 GCP 服务账号
echo      1. 去 https://console.cloud.google.com/iam-admin/serviceaccounts
echo      2. 创建服务账号 → 生成 JSON 密钥 → 下载
echo      3. 把下载的 JSON 放到 craftsman\secrets\play-sa.json
echo      4. 在 Play Console → 用户和权限 邀请该服务账号 Email
echo         授予"Release manager"角色
echo.
echo   C. 填写 .env 中的密码
echo      把 %ENV_FILE% 中的内容追加到 craftsman\.env
echo      并替换 YOUR_PASSWORD_HERE 为实际密码
echo.
echo   D. 重新启动 Craftsman 服务即可真上架
echo.
pause
