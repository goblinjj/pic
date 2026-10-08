"""登录失败计数：连续失败 MAX_FAILURES 次后锁 LOCK_SECONDS 秒。

只放进程内存：重启即清零。单进程部署，够用。
另有滑动窗口计数 hit()：给无需登录、又耗算力的接口（分享页以图搜图）限频。
"""
import threading
import time
from collections import deque

MAX_FAILURES = 5
LOCK_SECONDS = 15 * 60

_clock = time.monotonic
_lock = threading.Lock()
# key -> [连续失败次数, 锁定截止时刻]
_state: dict[tuple, list] = {}
# key -> 窗口内各次请求的时刻
_hits: dict[tuple, deque] = {}


def allowed(key: tuple) -> bool:
    with _lock:
        entry = _state.get(key)
        if not entry or entry[1] == 0:
            return True
        if _clock() >= entry[1]:
            del _state[key]
            return True
        return False


def record_failure(key: tuple):
    with _lock:
        entry = _state.setdefault(key, [0, 0])
        entry[0] += 1
        if entry[0] >= MAX_FAILURES:
            entry[1] = _clock() + LOCK_SECONDS


def record_success(key: tuple):
    with _lock:
        _state.pop(key, None)


def hit(key: tuple, limit: int, window_seconds: float) -> bool:
    """记一次请求；窗口内已达 limit 次则不记并返回 False。"""
    with _lock:
        now = _clock()
        q = _hits.setdefault(key, deque())
        while q and q[0] <= now - window_seconds:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


def reset():
    with _lock:
        _state.clear()
        _hits.clear()
