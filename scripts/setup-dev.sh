#!/usr/bin/env bash
#
# 一次性开发环境配置：建 venv、装依赖、启用版本控制中的 git hooks。
# 换机器或重新 clone 之后跑一次即可。
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "▶ 启用 scripts/git-hooks 下的 git hooks"
git config core.hooksPath scripts/git-hooks
chmod +x scripts/git-hooks/* scripts/*.sh
echo "  ✓ core.hooksPath = scripts/git-hooks"

echo "▶ 准备后端虚拟环境 backend/.venv"
if [ ! -d backend/.venv ]; then
    python3 -m venv backend/.venv
fi
backend/.venv/bin/pip install --quiet --upgrade pip

if [ -f backend/requirements-dev.txt ]; then
    backend/.venv/bin/pip install --quiet -r backend/requirements-dev.txt
else
    # requirements-dev.txt 要等自定义字段那批改动才会加进来
    backend/.venv/bin/pip install --quiet -r backend/requirements.txt pytest httpx
fi
echo "  ✓ $(backend/.venv/bin/python -V)"

echo "▶ 安装前端依赖"
if [ ! -d frontend/node_modules ]; then
    (cd frontend && npm install --silent)
fi
echo "  ✓ node $(node -v)"

cat <<'EOF'

配置完成。

  git push              → 自动跑测试、构建、推送、部署到 NAS、健康检查
  git push --no-verify  → 只推送，不部署
  ./scripts/deploy.sh   → 手动触发一次完整部署

本地起开发环境：
  终端 1  cd backend && DB_PATH=./devdata/piclog.db UPLOAD_DIR=./devuploads \
            .venv/bin/python -m uvicorn main:app --reload --port 8080
  终端 2  cd frontend && npm run dev
EOF
