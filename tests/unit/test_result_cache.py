from __future__ import annotations

import json

import pytest

from droneimpact.api.cache import ResultCache, compute_fingerprint, compute_request_hash
from droneimpact.config import load_config


@pytest.fixture()
def cache_dir(tmp_path):
    return tmp_path / "cache"


@pytest.fixture()
def cache(cache_dir):
    return ResultCache(cache_dir, fingerprint="aabbccddee00", max_entries=5)


@pytest.fixture()
def sample_response():
    return {
        "drone_id": "test-001",
        "computed_at_utc": "2025-01-01T00:00:00Z",
        "recommended_engagement": {
            "point_index": 0,
            "lat": 48.5,
            "lon": 35.0,
            "altitude_m": 400.0,
            "distance_from_current_m": 0.0,
            "expected_casualties": 0.01,
            "engagement_score": 0.9,
            "reasoning": "test",
        },
        "trajectory_scores": [],
        "impact_distributions": [],
        "metadata": {
            "n_trajectory_points": 1,
            "n_monte_carlo_samples": 100,
            "simulation_time_ms": 10.0,
            "population_dataset": "test.gpkg",
            "infrastructure_dataset": "test.geojson",
        },
    }


class TestRequestHash:
    def test_deterministic(self):
        h1 = compute_request_hash(48.5, 35.0, 400.0, 230.0, 51.4, 500, 250_000)
        h2 = compute_request_hash(48.5, 35.0, 400.0, 230.0, 51.4, 500, 250_000)
        assert h1 == h2

    def test_different_params_different_hash(self):
        h1 = compute_request_hash(48.5, 35.0, 400.0, 230.0, 51.4, 500, 250_000)
        h2 = compute_request_hash(48.5, 35.0, 400.0, 231.0, 51.4, 500, 250_000)
        assert h1 != h2

    def test_hash_length(self):
        h = compute_request_hash(48.5, 35.0, 400.0, 230.0, 51.4, 500, 250_000)
        assert len(h) == 12


class TestFingerprint:
    def test_deterministic(self):
        cfg = load_config("config.yaml")
        f1 = compute_fingerprint(cfg)
        f2 = compute_fingerprint(cfg)
        assert f1 == f2

    def test_length(self):
        cfg = load_config("config.yaml")
        assert len(compute_fingerprint(cfg)) == 12

    def test_changes_with_config(self):
        cfg = load_config("config.yaml")
        f1 = compute_fingerprint(cfg)
        cfg2 = cfg.model_copy(update={
            "physics": cfg.physics.model_copy(update={"n_monte_carlo_samples": 999})
        })
        f2 = compute_fingerprint(cfg2)
        assert f1 != f2


class TestCacheMiss:
    def test_miss_returns_none(self, cache):
        assert cache.get("nonexistent00") is None

    def test_miss_on_empty_dir(self, cache):
        assert cache.get("anything0000") is None


class TestCacheHit:
    def test_put_then_get(self, cache, sample_response):
        req_hash = "abcdef123456"
        cache.put(req_hash, sample_response)
        result = cache.get(req_hash)
        assert result is not None
        assert result["drone_id"] == "test-001"

    def test_get_returns_exact_data(self, cache, sample_response):
        req_hash = "abcdef123456"
        cache.put(req_hash, sample_response)
        result = cache.get(req_hash)
        assert result == sample_response


class TestCacheDisabled:
    def test_disabled_returns_none(self, cache_dir, sample_response):
        cache = ResultCache(cache_dir, fingerprint="aabbccddee00", enabled=False)
        cache.put("abcdef123456", sample_response)
        assert cache.get("abcdef123456") is None

    def test_disabled_does_not_write(self, cache_dir, sample_response):
        cache = ResultCache(cache_dir, fingerprint="aabbccddee00", enabled=False)
        cache.put("abcdef123456", sample_response)
        assert not cache_dir.exists() or len(list(cache_dir.glob("*.json"))) == 0


class TestPruneStale:
    def test_prune_removes_old_fingerprint(self, cache_dir, sample_response):
        cache_dir.mkdir(parents=True)
        (cache_dir / "oldfingerpr_req123456.json").write_text(json.dumps(sample_response))
        (cache_dir / "aabbccddee00_req123456.json").write_text(json.dumps(sample_response))

        cache = ResultCache(cache_dir, fingerprint="aabbccddee00")
        pruned = cache.prune_stale()
        assert pruned == 1
        assert (cache_dir / "aabbccddee00_req123456.json").exists()
        assert not (cache_dir / "oldfingerpr_req123456.json").exists()

    def test_prune_empty_dir(self, cache_dir):
        cache = ResultCache(cache_dir, fingerprint="aabbccddee00")
        assert cache.prune_stale() == 0


class TestEviction:
    def test_evicts_oldest_when_full(self, cache_dir, sample_response):
        import time as _time

        cache = ResultCache(cache_dir, fingerprint="aabbccddee00", max_entries=3)
        for i in range(3):
            cache.put(f"request{i:06d}", sample_response)
            _time.sleep(0.01)

        cache.put("newrequest00", sample_response)
        files = list(cache_dir.glob("*.json"))
        assert len(files) <= 3
        names = {f.name for f in files}
        assert "aabbccddee00_newrequest00.json" in names

    def test_max_entries_respected(self, cache_dir, sample_response):
        cache = ResultCache(cache_dir, fingerprint="aabbccddee00", max_entries=2)
        for i in range(5):
            cache.put(f"req{i:09d}", sample_response)
        files = list(cache_dir.glob("*.json"))
        assert len(files) <= 2


class TestCorruptEntry:
    def test_corrupt_json_returns_none(self, cache_dir):
        cache_dir.mkdir(parents=True)
        path = cache_dir / "aabbccddee00_corrupted000.json"
        path.write_text("not valid json{{{")
        cache = ResultCache(cache_dir, fingerprint="aabbccddee00")
        result = cache.get("corrupted000")
        assert result is None
        assert not path.exists()


class TestReadOnlyDirectory:
    def test_put_on_readonly_disables_cache(self, tmp_path, sample_response):
        ro_dir = tmp_path / "readonly" / "cache"
        ro_parent = tmp_path / "readonly"
        ro_parent.mkdir()
        ro_parent.chmod(0o555)
        cache = ResultCache(ro_dir, fingerprint="aabbccddee00")
        cache.put("req000000000", sample_response)
        assert not cache.enabled
        ro_parent.chmod(0o755)

    def test_put_readonly_does_not_raise(self, tmp_path, sample_response):
        ro_dir = tmp_path / "readonly" / "cache"
        ro_parent = tmp_path / "readonly"
        ro_parent.mkdir()
        ro_parent.chmod(0o555)
        cache = ResultCache(ro_dir, fingerprint="aabbccddee00")
        cache.put("req000000000", sample_response)
        ro_parent.chmod(0o755)
