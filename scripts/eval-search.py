#!/usr/bin/env python3
"""用真实照片评测以图搜图，帮助确定相似度阈值。

用法：
    PICLOG_USERNAME=babelingz PICLOG_PASSWORD=... \
    backend/.venv/bin/python scripts/eval-search.py <照片目录> [--url http://192.168.8.10:8080]

照片文件名以「正确答案」的日志 id 开头，如 37_a.jpg、37_side.jpg（请用 JPEG/PNG，
服务端不支持 HEIC）。脚本逐张调用搜索接口（min_score=-1，取回全部分数），输出：
  - 正确日志的排名：第 1 / 前 3 / 更靠后 / 不在前 50
  - 正确匹配的分数、每张照片「排第一的错误匹配」的分数
据此调整 backend/image_search.py 的 MIN_SCORE
和 frontend/src/imageSearch.js 的 SCORE_LEVELS。
"""
import argparse
import os
import re
import statistics
import sys
from pathlib import Path

import httpx

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def expected_log_id(path: Path):
    m = re.match(r"(\d+)_", path.name)
    return int(m.group(1)) if m else None


def describe(label, values):
    if not values:
        print(f"  {label}: 无")
        return
    q = sorted(values)
    print(
        f"  {label}: n={len(q)}  最小 {q[0]:.3f}  中位数 {statistics.median(q):.3f}  最大 {q[-1]:.3f}"
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", type=Path)
    ap.add_argument("--url", default="http://192.168.8.10:8080")
    ap.add_argument("--username", default=os.environ.get("PICLOG_USERNAME", ""))
    ap.add_argument("--password", default=os.environ.get("PICLOG_PASSWORD", ""))
    args = ap.parse_args()
    base = args.url.rstrip("/")

    photos = sorted(p for p in args.dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    if not photos:
        sys.exit(f"{args.dir} 里没有 JPEG/PNG/WebP 照片")

    ranks = {"第 1": 0, "前 3": 0, "更靠后": 0, "不在前 50": 0}
    correct_scores, wrong_top_scores = [], []
    pending = 0

    with httpx.Client(timeout=120) as client:
        # 搜索只在登录账号自己的图片里进行
        login = client.post(
            f"{base}/api/auth/login", json={"username": args.username, "password": args.password}
        )
        if login.status_code != 200:
            sys.exit(f"登录失败：{login.status_code} {login.text}（用 PICLOG_USERNAME / PICLOG_PASSWORD 提供账号）")
        for p in photos:
            expected = expected_log_id(p)
            if expected is None:
                print(f"跳过 {p.name}：文件名不是以「日志id_」开头")
                continue
            with p.open("rb") as f:
                resp = client.post(
                    f"{base}/api/search/image",
                    params={"limit": 50, "min_score": -1},
                    files={"file": (p.name, f, "application/octet-stream")},
                )
            if resp.status_code != 200:
                print(f"{p.name}: 请求失败 {resp.status_code} {resp.text}")
                continue
            data = resp.json()
            pending = data["pending"]
            items = data["items"]
            ids = [it["log"]["id"] for it in items]
            wrong = [it["score"] for it in items if it["log"]["id"] != expected]
            if wrong:
                wrong_top_scores.append(wrong[0])
            first = f"#{ids[0]}（{items[0]['score']:.3f}）" if items else "无"

            if expected in ids:
                rank = ids.index(expected) + 1
                score = items[rank - 1]["score"]
                correct_scores.append(score)
                ranks["第 1" if rank == 1 else "前 3" if rank <= 3 else "更靠后"] += 1
                print(f"{p.name}: 正确日志 #{expected} 排第 {rank}，分数 {score:.3f}；第一名 {first}")
            else:
                ranks["不在前 50"] += 1
                print(f"{p.name}: 正确日志 #{expected} 不在前 50；第一名 {first}")

    total = sum(ranks.values())
    print(f"\n共 {total} 张")
    for k, v in ranks.items():
        print(f"  {k}: {v}（{v / total:.0%}）" if total else f"  {k}: {v}")
    print("分数分布：")
    describe("正确匹配", correct_scores)
    describe("排第一的错误匹配", wrong_top_scores)
    if pending:
        print(f"\n注意：还有 {pending} 张图片没建好索引，结果可能偏低")
    print(
        "\n建议：MIN_SCORE 取略低于「正确匹配」的最小值；"
        "「很可能是同一件」的门槛取高于大多数「排第一的错误匹配」的值。"
    )


if __name__ == "__main__":
    main()
