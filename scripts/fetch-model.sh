#!/usr/bin/env bash
#
# 下载以图搜图的模型（DINOv2-small ONNX），校验后放到 NAS 的 data/models/ 下并重启容器。
#
#   ./scripts/fetch-model.sh           下载 → 校验 → 上传到 NAS → 重启容器
#   ./scripts/fetch-model.sh --local   只放到 backend/devdata/models/（本地开发用）
#
# 下载在本机进行（NAS 不一定能访问 HuggingFace）。国内网络可以先
#   export HF_ENDPOINT=https://hf-mirror.com
# 已下载且校验通过的文件会复用，重复运行是安全的。
#
set -euo pipefail

NAS_HOST="${PICLOG_NAS_HOST:-root@192.168.8.10}"
NAS_DIR="${PICLOG_NAS_DIR:-/volume2/homes/darlingz/pic}"
NAS_COMPOSE="${PICLOG_NAS_COMPOSE:-/usr/local/bin/docker-compose}"
NAS_SERVICE="${PICLOG_NAS_SERVICE:-piclog}"
HF_ENDPOINT="${HF_ENDPOINT:-https://huggingface.co}"

MODEL_URL_PATH="onnx-community/dinov2-small/resolve/main/onnx/model.onnx"
MODEL_NAME="dinov2-small.onnx"
MODEL_SHA256="f22797eabf810a75e41de68d378541ebea372122b25c4ce3ef25ff618250c20a"

SSH_OPTS=(-o ConnectTimeout=15 -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
REMOTE_PATH="/usr/local/bin:/usr/bin:/bin"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/piclog"
CACHED="$CACHE_DIR/$MODEL_NAME"

die() { printf '✗ %s\n' "$*" >&2; exit 1; }
sha_of() { shasum -a 256 "$1" | cut -d' ' -f1; }
nas() { ssh "${SSH_OPTS[@]}" "$NAS_HOST" "export PATH=${REMOTE_PATH}:\$PATH; $*"; }

# ------------------------------------------------------------------ 下载
mkdir -p "$CACHE_DIR"
if [ -f "$CACHED" ] && [ "$(sha_of "$CACHED")" = "$MODEL_SHA256" ]; then
    echo "✓ 使用已缓存的模型 $CACHED"
else
    echo "▶ 下载 $HF_ENDPOINT/$MODEL_URL_PATH（约 85MB）"
    curl -fL --retry 3 -o "$CACHED.part" "$HF_ENDPOINT/$MODEL_URL_PATH"
    actual="$(sha_of "$CACHED.part")"
    if [ "$actual" != "$MODEL_SHA256" ]; then
        rm -f "$CACHED.part"
        die "sha256 不匹配：期望 $MODEL_SHA256，实际 $actual"
    fi
    mv "$CACHED.part" "$CACHED"
    echo "✓ 下载完成，校验通过"
fi

# ------------------------------------------------------------------ 本地开发
if [ "${1:-}" = "--local" ]; then
    dest="$REPO_ROOT/backend/devdata/models"
    mkdir -p "$dest"
    cp "$CACHED" "$dest/$MODEL_NAME"
    echo "✓ 已放到 $dest/$MODEL_NAME"
    echo "  启动后端时加上 MODEL_PATH=./devdata/models/$MODEL_NAME"
    exit 0
fi

# ------------------------------------------------------------------ 上传到 NAS
remote_dir="$NAS_DIR/data/models"
remote_file="$remote_dir/$MODEL_NAME"
remote_sha="$(nas "sha256sum '$remote_file' 2>/dev/null | cut -d' ' -f1" || true)"
if [ "$remote_sha" = "$MODEL_SHA256" ]; then
    echo "✓ NAS 上已有同一个模型文件，跳过上传"
else
    echo "▶ 上传到 $NAS_HOST:$remote_file"
    # 用 ssh + cat 而不是 scp：群晖默认不一定开启 SFTP 子系统
    ssh "${SSH_OPTS[@]}" "$NAS_HOST" \
        "mkdir -p '$remote_dir' && cat > '$remote_file.part' && mv '$remote_file.part' '$remote_file'" \
        < "$CACHED"
    remote_sha="$(nas "sha256sum '$remote_file' | cut -d' ' -f1")"
    [ "$remote_sha" = "$MODEL_SHA256" ] || die "上传后 NAS 上的文件校验不通过：$remote_sha"
    echo "✓ 上传完成，校验通过"
fi

# ------------------------------------------------------------------ 重启
echo "▶ 重启容器以启用以图搜图"
nas "cd '$NAS_DIR' && '$NAS_COMPOSE' restart '$NAS_SERVICE'"
echo "✓ 完成。后台会开始为已有图片建立索引（每张约 1 秒）"
