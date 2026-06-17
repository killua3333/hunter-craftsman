#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Dashboard 一键部署脚本
# 使用:  bash deploy-dashboard.sh [REPO_ROOT] [DOMAIN]
#
# 前提:
#   1. 代码已同步到 REPO_ROOT（默认 /home/admin/hunter-craftsman）
#   2. 已执行 bootstrap-ubuntu.sh 安装基础依赖
#   3. Craftsman service 已安装并运行
#   4. 已安装 Node.js（用于前端构建）
# ============================================================

REPO_ROOT="${1:-/home/admin/hunter-craftsman}"
DOMAIN="${2:-}"

GATEWAY_DIR="${REPO_ROOT}/dashboard/gateway"
UI_DIR="${REPO_ROOT}/dashboard/ui"

echo "========================================="
echo " Dashboard Deployment"
echo " REPO_ROOT : ${REPO_ROOT}"
echo " DOMAIN    : ${DOMAIN:-<未指定，跳过 Nginx>}"
echo "========================================="

# --------------------------------------------------
# Step 1: 构建前端
# --------------------------------------------------
echo ""
echo "== [1/4] 构建前端 =="
cd "${UI_DIR}"

if [[ ! -d "node_modules" ]]; then
  echo "安装前端依赖..."
  npm install
fi

echo "TypeScript 编译 + Vite 打包..."
npm run build

echo "构建产物输出到: ${GATEWAY_DIR}/static/"
ls -la "${GATEWAY_DIR}/static/" | head -5

# --------------------------------------------------
# Step 2: 安装 Gateway Python 依赖
# --------------------------------------------------
echo ""
echo "== [2/4] 安装 Gateway Python 依赖 =="
"${REPO_ROOT}/.venv/bin/pip" install -r "${GATEWAY_DIR}/requirements.txt"

# --------------------------------------------------
# Step 3: 安装 Gateway systemd 服务
# --------------------------------------------------
echo ""
echo "== [3/4] 安装 Gateway systemd 服务 =="
bash "${REPO_ROOT}/docker/install-gateway-service.sh" "${REPO_ROOT}"

echo "启动 Gateway 服务..."
sudo systemctl start gateway
sudo systemctl status gateway --no-pager

# --------------------------------------------------
# Step 4: 配置 Nginx（如果指定了域名）
# --------------------------------------------------
if [[ -n "${DOMAIN}" ]]; then
  echo ""
  echo "== [4/4] 配置 Nginx 域名: ${DOMAIN} =="
  bash "${REPO_ROOT}/docker/install-dashboard-nginx.sh" "${REPO_ROOT}" "${DOMAIN}"
else
  echo ""
  echo "== [4/4] 跳过 Nginx (未指定域名) =="
  echo "   若要配置域名，运行:"
  echo "   bash docker/install-dashboard-nginx.sh ${REPO_ROOT} your-domain.com"
fi

# --------------------------------------------------
# 冒烟测试
# --------------------------------------------------
echo ""
echo "== 冒烟测试 =="
sleep 2
bash "${REPO_ROOT}/docker/smoke-check-dashboard.sh"

echo ""
echo "========================================="
echo " 部署完成!"
echo "========================================="
if [[ -n "${DOMAIN}" ]]; then
  echo " 访问地址: http://${DOMAIN}"
else
  echo " 访问地址: http://<服务器IP>:8800"
  echo ""
  echo " 若要绑定域名，运行:"
  echo "   bash docker/install-dashboard-nginx.sh ${REPO_ROOT} your-domain.com"
fi
echo ""
echo " 常用管理命令:"
echo "   sudo systemctl status gateway     # 查看状态"
echo "   sudo systemctl restart gateway    # 重启"
echo "   sudo journalctl -u gateway -f     # 查看日志"
echo "   bash docker/smoke-check-dashboard.sh  # 健康检查"
