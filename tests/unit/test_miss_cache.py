import h3

from droneimpact.scoring.engine import _miss_cache, _miss_cache_key, clear_miss_cache


def test_cache_key_same_cell():
    k1 = _miss_cache_key(48.0, 31.0, 400.0, 315.0, 10000, 10.0, 1.0)
    k2 = _miss_cache_key(48.0001, 31.0001, 403.0, 315.4, 10000, 10.0, 1.0)
    assert k1 == k2


def test_cache_key_different_cell():
    k1 = _miss_cache_key(48.0, 31.0, 400.0, 315.0, 10000, 10.0, 1.0)
    k2 = _miss_cache_key(49.0, 32.0, 400.0, 315.0, 10000, 10.0, 1.0)
    assert k1 != k2


def test_cache_key_different_agl():
    k1 = _miss_cache_key(48.0, 31.0, 400.0, 315.0, 10000, 10.0, 1.0)
    k2 = _miss_cache_key(48.0, 31.0, 500.0, 315.0, 10000, 10.0, 1.0)
    assert k1 != k2


def test_cache_key_different_heading():
    k1 = _miss_cache_key(48.0, 31.0, 400.0, 315.0, 10000, 10.0, 1.0)
    k2 = _miss_cache_key(48.0, 31.0, 400.0, 90.0, 10000, 10.0, 1.0)
    assert k1 != k2


def test_clear_cache():
    _miss_cache[("test",)] = 42.0
    clear_miss_cache()
    assert len(_miss_cache) == 0
