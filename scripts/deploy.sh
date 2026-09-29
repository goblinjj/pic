#!/usr/bin/env bash
#
# PicLog 部署脚本：把当前 HEAD 部署到 NAS。
#
#   本地 gate（测试 + 前端构建）→ 推送到 NAS 仓库 → 重建容器 → 健康检查
#
# 由 scripts/git-hooks/pre-push 在 git push 时自动调用；gate 或部署失败会阻止推送。
# 也可以单独运行 ./scripts/deploy.sh，只部署、不推 GitHub（适合上线前试一把）。
#
# 跳过部署直接推送：git push --no-verify
#
# 关于为什么不走 GitHub：pre-push 在推送「之前」运行，此刻提交还没到 GitHub，
# 让 NAS 去 GitHub 拉只会拉到旧代码。而如果 hook 自己抢先推一次，又会让外层
# 推送的 compare-and-swap 失败（git 在 hook 运行前就记下了远端 ref 的期望值）。
# 直接把提交推进 NAS 自己的仓库，两个问题都不存在，还少依赖一个外部服务。
#
set -euo pipefail

NAS_HOST="${PICLOG_NAS_HOST:-root@192.168.8.10}"
NAS_DIR="${PICLOG_NAS_DIR:-/volume2/homes/darlingz/pic}"
NAS_COMPOSE="${PICLOG_NAS_COMPOSE:-/usr/local/bin/docker-compose}"
NAS_SERVICE="${PICLOG_NAS_SERVICE:-piclog}"
DEPLOY_REF="${PICLOG_DEPLOY_REF:-refs/heads/deploy}"
BRANCH="${PICLOG_BRANCH:-main}"
HEALTH_PATH="${PICLOG_HEALTH_PATH:-/api/health}"
HEALTH_PORT="${PICLOG_HEALTH_PORT:-8080}"
HEALTH_RETRIES="${PICLOG_HEALTH_RETRIES:-20}"

SSH_OPTS=(-o ConnectTimeout=15 -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
REMOTE_PATH="/usr/local/bin:/usr/bin:/bin"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

START_TS=$(date +%s)
PREVIOUS_HEAD=""
FIRST_MIGRATION=""

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
    if [ -n "$FIRST_MIGRATION" ]; then
        # 这次部署会把单用户数据迁移成多账号布局：直接回滚代码的话，旧版本会看到
        # 一个空库（数据已被移走），之后写入的数据还会和迁移后的数据分家。必须连数据一起还原
        printf '%s\n这是首次多账号迁移。不要只回滚代码——旧版本会看到空库。连数据一起还原：\n\n' "$C_RED" >&2
        printf '  ssh %s\n' "$NAS_HOST" >&2
        printf '  export PATH=%s:$PATH; cd %s\n' "$REMOTE_PATH" "$NAS_DIR" >&2
        printf '  %s stop %s\n' "$NAS_COMPOSE" "$NAS_SERVICE" >&2
        printf '  b=$(ls -d backups/pre-multiuser-* | tail -1); echo "从 $b 还原"\n' >&2
        printf '  mv data data.failed-$(date +%%s) && mv uploads uploads.failed-$(date +%%s)\n' >&2
        printf '  cp -a "$b/data" "$b/uploads" .\n' >&2
        printf '  git reset --hard %s && %s up -d --build\n%s\n' "$PREVIOUS_HEAD" "$NAS_COMPOSE" "$C_RESET" >&2
    elif [ -n "$PREVIOUS_HEAD" ]; then
        printf '%s\nNAS 回滚到部署前的版本：\n\n  ssh %s "export PATH=%s:\\$PATH; cd %s && git reset --hard %s && %s up -d --build"\n%s\n' \
            "$C_DIM" "$NAS_HOST" "$REMOTE_PATH" "$NAS_DIR" "$PREVIOUS_HEAD" "$NAS_COMPOSE" "$C_RESET" >&2
    fi
    printf '%sGitHub 未被改动，本次推送已中止。%s\n' "$C_DIM" "$C_RESET" >&2
    exit 1
}

run_logged() {
    # run_logged <描述> <命令...>：成功时保持安静，失败时才把输出吐出来
    local label="$1"; shift
    local log
    log="$(mktemp -t piclog-deploy)"
    if ! "$@" >"$log" 2>&1; then
        printf '\n%s--- %s 输出 ---%s\n' "$C_DIM" "$label" "$C_RESET" >&2
        cat "$log" >&2
        rm -f "$log"
        die "${label}失败，已中止部署"
    fi
    rm -f "$log"
}

nas_run() {
    ssh "${SSH_OPTS[@]}" "$NAS_HOST" "export PATH=${REMOTE_PATH}:\$PATH; $*"
}

# ------------------------------------------------------------------ 分支检查
current_branch="$(git rev-parse --abbrev-ref HEAD)"
if [ "$current_branch" != "$BRANCH" ]; then
    info "当前分支 ${current_branch} 不是 ${BRANCH}，跳过部署"
    exit 0
fi

if [ -n "$(git status --porcelain)" ]; then
    info "提示：工作区有未提交的改动，它们不会被部署"
fi

local_head="$(git rev-parse --short HEAD)"

# ------------------------------------------------------------------ 本地 gate
step "运行后端测试"
if [ -d backend/tests ]; then
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
    info "backend/tests 不存在，跳过"
fi

step "构建前端"
run_logged "前端构建" bash -c "cd '$REPO_ROOT/frontend' && npm run build"
ok "构建成功"

# ------------------------------------------------------------------ 送到 NAS
step "推送到 NAS 仓库"
PREVIOUS_HEAD="$(nas_run "git -C '$NAS_DIR' rev-parse --short HEAD")" \
    || die "无法连接 NAS 或读取仓库状态"
info "NAS 当前版本 ${PREVIOUS_HEAD} → 目标 ${local_head}"

if [ "$PREVIOUS_HEAD" = "$local_head" ]; then
    info "NAS 已是该版本，仍会重建以确保镜像最新"
fi

run_logged "推送到 NAS" git push --no-verify "$NAS_HOST:$NAS_DIR" "+HEAD:$DEPLOY_REF"
ok "已推送 ${local_head}"

# ------------------------------------------------------------------ 重建容器
step "重建容器"
# 旧位置还有单用户的库 = 这次启动会做多账号迁移（远端会先备份），失败时的回滚方式不同
if nas_run "test -f '$NAS_DIR/data/piclog.db'"; then
    FIRST_MIGRATION=1
    info "检测到单用户数据，本次会先备份再迁移到多账号布局"
fi
run_logged "容器重建" ssh "${SSH_OPTS[@]}" "$NAS_HOST" bash -s <<EOF
set -euo pipefail
# 非交互式 SSH 的 PATH 不含 /usr/local/bin，而 docker-compose v1 要在 PATH 上找 docker
export PATH="${REMOTE_PATH}:\$PATH"
cd '$NAS_DIR'
git reset --hard '${DEPLOY_REF#refs/heads/}'
# .env 是未跟踪文件，reset --hard 不会动它
if [ ! -f .env ]; then
    echo "缺少 $NAS_DIR/.env：参考仓库里的 .env.example 创建" >&2
    exit 1
fi
'$NAS_COMPOSE' build
# 判断依据是「旧库还在」而不是「accounts.db 不存在」：首次启动失败时 accounts.db
# 可能已经建出来了，回滚后旧版本继续写的数据仍需要在下次迁移前备份
if [ -f data/piclog.db ]; then
    # 即将第一次迁移到多账号布局：先停容器，保证库文件一致，再整份备份
    backup="backups/pre-multiuser-\$(date +%Y%m%d-%H%M%S)"
    '$NAS_COMPOSE' stop '$NAS_SERVICE'
    mkdir -p "\$backup"
    cp -a data uploads "\$backup/"
    echo "已备份到 $NAS_DIR/\$backup"
fi
'$NAS_COMPOSE' up -d
EOF
ok "容器已重建"

# ------------------------------------------------------------------ 健康检查
step "健康检查"
health_url="http://127.0.0.1:${HEALTH_PORT}${HEALTH_PATH}"
# 用 heredoc 而不是 nas_run：后者会再套一层双引号，转义层数一多就容易把
# 远端变量写成字面量（上一版就是这么挂的——应用返回 200，比较却永远为假）
if ! ssh "${SSH_OPTS[@]}" "$NAS_HOST" bash -s <<EOF
export PATH="${REMOTE_PATH}:\$PATH"
code=""
for i in \$(seq 1 $HEALTH_RETRIES); do
    code=\$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 '$health_url' || true)
    if [ "\$code" = "200" ]; then
        echo "HTTP \$code"
        exit 0
    fi
    sleep 2
done
echo "最后一次响应: \${code:-无响应}"
exit 1
EOF
then
    printf '\n%s最近的容器日志：%s\n' "$C_DIM" "$C_RESET" >&2
    nas_run "cd '$NAS_DIR' && '$NAS_COMPOSE' logs --tail=30 '$NAS_SERVICE'" >&2 || true
    die "健康检查失败：${health_url} 没有返回 200"
fi
ok "${health_url} 返回 200"

# ------------------------------------------------------------------ 完成
deployed="$(nas_run "git -C '$NAS_DIR' rev-parse --short HEAD")"
elapsed=$(( $(date +%s) - START_TS ))
printf '\n%s部署完成%s  %s → %s  用时 %dm%02ds\n\n' \
    "$C_GREEN" "$C_RESET" "$PREVIOUS_HEAD" "$deployed" $((elapsed / 60)) $((elapsed % 60))
