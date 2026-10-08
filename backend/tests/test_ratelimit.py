import ratelimit


def test_hit_sliding_window(monkeypatch):
    ratelimit.reset()
    now = [1000.0]
    monkeypatch.setattr(ratelimit, "_clock", lambda: now[0])
    key = ("t", "1.2.3.4")
    assert all(ratelimit.hit(key, 3, 60) for _ in range(3))
    assert ratelimit.hit(key, 3, 60) is False
    # 别的 key 不受影响
    assert ratelimit.hit(("t", "5.6.7.8"), 3, 60) is True
    now[0] += 60.01
    assert ratelimit.hit(key, 3, 60) is True


def test_reset_clears_hits(monkeypatch):
    key = ("t", "x")
    for _ in range(2):
        ratelimit.hit(key, 2, 60)
    ratelimit.reset()
    assert ratelimit.hit(key, 2, 60) is True
