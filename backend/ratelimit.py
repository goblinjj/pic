"""登录失败计数：连续失败 MAX_FAILURES 次后锁 LOCK_SECONDS 秒。

只放进程内存：重启即清零。单进程部署，够用。
"""
import threading
import time

MAX_FAILURES = 5
LOCK_SECONDS = 15 * 60

_clock = time.monotonic
_lock = threading.Lock()
# key -> [连续失败次数, 锁定截止时刻]
_state: dict[tuple, list] = {}


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


def reset():
    with _lock:
        _state.clear()
