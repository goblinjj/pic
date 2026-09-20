#!/usr/bin/env bash
#
# PicLog 部署脚本
#
#   本地 gate（测试 + 前端构建）→ 推送 GitHub → NAS 拉取重建 → 健康检查
#
# 通常由 scripts/git-hooks/pre-push 自动调用（git push 时触发），
# 也可以单独运行：./scripts/deploy.sh
#
# 跳过部署直接推送：git push --no-verify
#
set -euo pipefail

NAS_HOST="${PICLOG_NAS_HOST:-root@192.168.8.10}"
NAS_DIR="${PICLOG_NAS_DIR:-/volume2/homes/darlingz/pic}"
NAS_COMPOSE="${PICLOG_NAS_COMPOSE:-/usr/local/bin/docker-compose}"
BRANCH="${PICLOG_BRANCH:-main}"
REMOTE="${PICLOG_REMOTE:-origin}"
HEALTH_PATH="${PICLOG_HEALTH_PATH:-/api/categories}"
HEALTH_PORT="${PICLOG_HEALTH_PORT:-8080}"
HEALTH_RETRIES="${PICLOG_HEALTH_RETRIES:-20}"

SSH_OPTS=(-o ConnectTimeout=15 -o BatchMode=yes)
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

START_TS=$(date +%s)
PREVIOUS_HEAD=""
PUSHED=0

if [ -t 1 ]; then
    C_BLUE=$'\033[1;34m'; C_GREEN=$'\033[32m'; C_RED=$'\033[31m'
    C_DIM=$'\033[2m'; C_RESET=$'\033[0m'
else
    C_BLUE=""; C_GREEN=""; C_RED=""; C_DIM=""; C_RESET=""
fi

step() { printf '\n%s▶ %s%s\n' "$C_BLUE" "$*" "$C_RESET"; }
ok()   { printf '  %s✓%s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
info() { printf '  %s%s%s\n' "$C_DIM" "$*" "$C_RESET"; }

die() {
    printf '\n%s✗ %s%s\n' "$C_RED" "$*" "$C_RESET" >&2
    if [ "$PUSHED" -eq 1 ]; then
        cat >&2 <<EOF

${C_DIM}提交已经推到 GitHub，但 NAS 可能还停在旧版本——代码没丢。
把 NAS 回滚到部署前的状态：

  ssh $NAS_HOST "cd $NAS_DIR && git reset --hard $PREVIOUS_HEAD && $NAS_COMPOSE up -d --build"
${C_RESET}
EOF
    fi
    exit 1
}

run_logged() {
    # run_logged <描述> <命令...>：失败时才把输出吐出来，成功时保持安静
    local label="$1"; shift
    local log
    log="$(mktemp -t piclog-deploy)"
    if ! "$@" >"$log" 2>&1; then
        printf '\n%s--- %s 输出 ---%s\n' "$C_DIM" "$label" "$C_RESET" >&2
        cat "$log" >&2
        rm -f "$log"
        die "$label 失败，已中止部署"
    fi
    rm -f "$log"
}

# ---------------------------------------------------------------- 分支检查
current_branch="$(git rev-parse --abbrev-ref HEAD)"
if [ "$current_branch" != "$BRANCH" ]; then
    info "当前分支 $current_branch 不是 $BRANCH，跳过部署"
    exit 0
fi

if [ -n "$(git status --porcelain)" ]; then
    info "提示：工作区有未提交的改动，它们不会被部署"
fi

# ---------------------------------------------------------------- 本地 gate
if [ -d backend/tests ]; then
    step "运行后端测试"
    if [ -x "$REPO_ROOT/backend/.venv/bin/pytest" ]; then
        PYTEST="$REPO_ROOT/backend/.venv/bin/pytest"
    elif command -v pytest >/dev/null 2>&1; then
        PYTEST="$(command -v pytest)"
    else
        die "找不到 pytest。先运行 ./scripts/setup-dev.sh 安装开发依赖"
    fi
    run_logged "后端测试" bash -c "cd '$REPO_ROOT/backend' && '$PYTEST' tests -q"
    ok "测试通过"
else
    step "运行后端测试"
    info "backend/tests 不存在，跳过"
fi

step "构建前端"
run_logged "前端构建" bash -c "cd '$REPO_ROOT/frontend' && npm run build"
ok "构建成功"

# ---------------------------------------------------------------- 推送
# pre-push hook 在推送「之前」运行，此刻提交还没到 GitHub。
# 这里必须自己先推上去，NAS 随后 pull 才拿得到新代码。
# --no-verify 防止递归触发本 hook；外层那次 push 之后会变成 "Everything up-to-date"。
step "推送到 $REMOTE/$BRANCH"
local_head="$(git rev-parse --short HEAD)"
push_log="$(mktemp -t piclog-push)"
if ! git push --no-verify "$REMOTE" "$BRANCH" >"$push_log" 2>&1; then
    cat "$push_log" >&2
    rm -f "$push_log"
    die "推送到 $REMOTE/$BRANCH 失败"
fi
if grep -q 'Everything up-to-date' "$push_log"; then
    info "GitHub 已是最新（$local_head）"
else
    ok "已推送 $local_head"
fi
rm -f "$push_log"
PUSHED=1

# ---------------------------------------------------------------- NAS 部署
step "NAS 拉取并重建"
PREVIOUS_HEAD="$(ssh "${SSH_OPTS[@]}" "$NAS_HOST" "git -C '$NAS_DIR' rev-parse --short HEAD")" \
    || die "无法连接 NAS 或读取仓库状态"
info "NAS 当前版本 $PREVIOUS_HEAD → 目标 $local_head"

ssh "${SSH_OPTS[@]}" "$NAS_HOST" bash -s <<EOF || die "NAS 拉取或重建失败"
set -euo pipefail
cd '$NAS_DIR'
git fetch --quiet '$REMOTE' '$BRANCH'
git reset --hard '$REMOTE/$BRANCH'
'$NAS_COMPOSE' up -d --build
EOF
ok "容器已重建"

# ---------------------------------------------------------------- 健康检查
step "健康检查"
health_url="http://127.0.0.1:${HEALTH_PORT}${HEALTH_PATH}"
if ! ssh "${SSH_OPTS[@]}" "$NAS_HOST" \
    "for i in \$(seq 1 $HEALTH_RETRIES); do \
        code=\$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 '$health_url' || true); \
        if [ \"\$code\" = '200' ]; then echo \"HTTP 200\"; exit 0; fi; \
        sleep 2; \
     done; \
     echo \"最后一次响应: \${code:-无响应}\"; exit 1"
then
    printf '\n%s最近的容器日志：%s\n' "$C_DIM" "$C_RESET" >&2
    ssh "${SSH_OPTS[@]}" "$NAS_HOST" "cd '$NAS_DIR' && '$NAS_COMPOSE' logs --tail=30 piclog" >&2 || true
    die "健康检查失败：$health_url 没有返回 200"
fi
ok "$health_url 返回 200"

# ---------------------------------------------------------------- 完成
deployed="$(ssh "${SSH_OPTS[@]}" "$NAS_HOST" "git -C '$NAS_DIR' rev-parse --short HEAD")"
elapsed=$(( $(date +%s) - START_TS ))
printf '\n%s部署完成%s  %s → %s  用时 %dm%02ds\n\n' \
    "$C_GREEN" "$C_RESET" "$PREVIOUS_HEAD" "$deployed" $((elapsed / 60)) $((elapsed % 60))
