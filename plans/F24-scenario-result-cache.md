# F24 — Scenario Result Cache

**Status:** pending
**Branch:** `feature/F24-scenario-result-cache`
**Dependencies:** F19

---

## Goal

When a demo scenario is selected on the dashboard, skip the full physics/scoring computation if the result has already been computed for the current software version. Serve the stored result instead — turning a ~500 ms computation into a ~5 ms file read.

Demo scenarios have fixed inputs (defined in `config.yaml`) and deterministic computation (given the same code and config, the Monte Carlo seed could be fixed or the result is close enough). They are run repeatedly during demos and testing, always producing the same output. Caching them is safe and eliminates redundant work.

The cache must also be managed: when the software version changes (code update, config change), cached results from the old version become stale and must be cleaned up so they don't accumulate on the server.

---

## Design

### Cache key

Each cached result is identified by two components:

1. **Computation fingerprint** — a SHA-256 hash of everything that affects the computation output:
   - Git commit SHA (code version)
   - Serialised config sections: `physics`, `engagement`, `casualty`, `scoring`

   If either the code or the config changes, the fingerprint changes and all cached results are invalidated.

2. **Request hash** — a SHA-256 hash of the canonical request parameters:
   - `lat`, `lon`, `altitude_m`, `heading_deg`, `speed_m_s`
   - `evaluation_spacing_m`, `max_range_m`

   This distinguishes different scenarios from each other.

The cache filename is `{fingerprint_short}_{request_hash_short}.json` (first 12 hex chars of each hash — collision probability is negligible for <100 entries).

### Storage location

`data/cache/` — already inside the gitignored `data/` directory. Created on first write if it doesn't exist.

### Cache scope

The cache is implemented in the API layer, keyed by request parameters. It works for any `/analyze/single` request, not just named scenarios — but scenarios benefit most because they have fixed inputs and are run repeatedly. Custom one-off analyses also get cached, which speeds up repeated exploration of the same drone state.

### Lifecycle

On API startup:
1. Compute the current computation fingerprint
2. Scan `data/cache/` for files whose fingerprint prefix doesn't match the current one
3. Delete stale files
4. Log how many entries were pruned and how many remain

This ensures that after a deploy, old results are cleaned up on next boot. No manual intervention needed. No unbounded growth.

### Monte Carlo determinism

The current implementation uses a random RNG seed, so re-running the same scenario produces slightly different results each time. For caching to be correct, we need one of:

- **Option A (recommended):** Accept that cached results are from one specific MC run. The statistical properties (expected casualties, CEP) are stable across runs — the differences are in the noise of individual sample positions, which don't affect the recommendation. The cached result is as valid as any fresh run.
- **Option B:** Fix the RNG seed per scenario (e.g., `seed = hash(request_params)`). This makes results perfectly reproducible but is a physics-layer change.

Option A is simpler and sufficient. The cache stores a valid result; the user doesn't need it to be bit-identical to a fresh run.

---

## Acceptance Criteria

- [ ] Selecting a demo scenario that was previously computed returns the cached result without calling the physics/scoring engines
- [ ] The cached response is identical to a freshly computed response in structure (same schema, same fields)
- [ ] Changing any physics, engagement, casualty, or scoring config parameter invalidates all cached results on next startup
- [ ] Deploying a new code version (different git SHA) invalidates all cached results on next startup
- [ ] Stale cache files are deleted on API startup with a log message
- [ ] The cache works for arbitrary `/analyze/single` requests, not just named scenarios
- [ ] The response includes metadata indicating whether the result was served from cache
- [ ] Cache can be disabled via config (`cache.enabled: false`)
- [ ] Maximum cache size is configurable (`cache.max_entries`, default 50) — when exceeded, oldest entries by filesystem mtime are evicted
- [ ] `pytest` passes — unit tests for cache key computation, hit/miss logic, and pruning

---

## Implementation Steps

### 1. Compute the computation fingerprint at startup

In `src/droneimpact/main.py`, during the `lifespan` startup:

```python
import hashlib, json, subprocess

def _compute_fingerprint(config: AppConfig) -> str:
    parts = []
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        parts.append(sha)
    except Exception:
        parts.append("unknown")

    config_sections = {
        "physics": config.physics.model_dump(),
        "engagement": config.engagement.model_dump(),
        "casualty": config.casualty.model_dump(),
        "scoring": config.scoring.model_dump(),
    }
    parts.append(json.dumps(config_sections, sort_keys=True, default=str))

    return hashlib.sha256("".join(parts).encode()).hexdigest()
```

Store the fingerprint in `app.state.computation_fingerprint`.

For Docker builds where `.git` isn't present, fall back to reading a `BUILD_SHA` environment variable (set in the Dockerfile from `--build-arg`). If neither is available, use `"unknown"` — caching still works, it just won't invalidate on deploy (acceptable for dev).

### 2. Add cache config

In `config.yaml`, add:

```yaml
cache:
  enabled: true
  directory: "./data/cache"
  max_entries: 50
```

In `config.py`, add:

```python
class CacheConfig(BaseModel):
    enabled: bool = True
    directory: str = "./data/cache"
    max_entries: int = 50
```

Add `cache: CacheConfig = CacheConfig()` to `AppConfig`.

### 3. Implement the result cache

New file `src/droneimpact/api/cache.py`:

```python
class ResultCache:
    def __init__(self, directory: Path, fingerprint: str, max_entries: int):
        ...

    def get(self, request_hash: str) -> dict | None:
        """Return cached JSON response or None on miss."""

    def put(self, request_hash: str, response: dict) -> None:
        """Store a JSON response. Evict oldest if at capacity."""

    def prune_stale(self) -> int:
        """Delete files whose fingerprint doesn't match. Return count deleted."""

    @staticmethod
    def compute_request_hash(body: SingleDroneRequest) -> str:
        """Deterministic hash of the request parameters that affect output."""
```

Key details:
- `get()`: reads and returns `json.load()` of the cache file. Returns `None` if the file doesn't exist or can't be parsed.
- `put()`: writes `json.dump()` to the cache file. Before writing, checks entry count — if `>= max_entries`, deletes the file with the oldest `mtime`.
- `prune_stale()`: called once at startup. Lists all `.json` files in the cache directory, deletes any whose filename doesn't start with the current fingerprint prefix.
- `compute_request_hash()`: serialises the request fields that affect computation (`lat`, `lon`, `altitude_m`, `heading_deg`, `speed_m_s`, `evaluation_spacing_m`, `max_range_m`) to a canonical JSON string, then SHA-256 hashes it.

### 4. Integrate cache into the analyze endpoint

In `src/droneimpact/api/analyze.py`, modify `analyze_single`:

```python
@router.post("/single", response_model=SingleDroneResponse)
def analyze_single(body: SingleDroneRequest, request: Request) -> SingleDroneResponse:
    state = get_app_state(request)
    cache = get_cache(request)  # None if disabled

    if cache:
        req_hash = ResultCache.compute_request_hash(body)
        cached = cache.get(req_hash)
        if cached:
            cached["metadata"]["from_cache"] = True
            return SingleDroneResponse.model_validate(cached)

    # ... existing computation ...

    response = _build_response(body, result, elapsed_ms, state)

    if cache:
        cache.put(req_hash, response.model_dump())

    return response
```

### 5. Add `from_cache` to metadata

Add an optional field to `MetadataSchema`:

```python
class MetadataSchema(BaseModel):
    ...
    from_cache: bool = False
```

When serving a cached result, set `from_cache=True`. This lets the dashboard display a "cached" indicator if desired, and helps during debugging.

### 6. Prune stale entries on startup

In `main.py` lifespan, after computing the fingerprint:

```python
if cfg.cache.enabled:
    cache_dir = Path(cfg.cache.directory)
    cache = ResultCache(cache_dir, app.state.computation_fingerprint, cfg.cache.max_entries)
    pruned = cache.prune_stale()
    if pruned:
        logger.info("Pruned %d stale cache entries", pruned)
    logger.info("Result cache: %d entries, fingerprint %s", cache.entry_count, fingerprint[:12])
    app.state.result_cache = cache
else:
    app.state.result_cache = None
```

### 7. Dashboard: show cache indicator (optional)

In the dashboard's statistics panel or metadata section, if `metadata.from_cache` is `True`, show a small indicator: `"Result loaded from cache (computed at {computed_at_utc})"`. This is informational — the user knows the result isn't being recomputed.

### 8. Add cache management endpoint (optional but recommended)

```
DELETE /cache
```

Clears all cached results. Useful during development and debugging. Protected by a simple check (only allowed when running in debug mode, or behind an API key).

```
GET /cache/stats
```

Returns: `{ "entries": 4, "fingerprint": "a1b2c3...", "directory": "./data/cache", "size_bytes": 12340 }`.

### 9. Testing

`tests/unit/test_result_cache.py`:

```python
def test_cache_hit_returns_stored_result():
    """put() then get() returns the same data."""

def test_cache_miss_returns_none():
    """get() for unknown hash returns None."""

def test_prune_removes_stale_entries():
    """Files with different fingerprint prefix are deleted."""

def test_prune_keeps_current_entries():
    """Files with matching fingerprint prefix survive pruning."""

def test_max_entries_evicts_oldest():
    """When cache is full, put() deletes the oldest entry by mtime."""

def test_request_hash_deterministic():
    """Same request params always produce the same hash."""

def test_request_hash_varies_with_input():
    """Different lat/lon/heading produce different hashes."""

def test_fingerprint_changes_with_config():
    """Changing a physics parameter changes the fingerprint."""
```

`tests/integration/test_cache_api.py`:

```python
def test_second_identical_request_is_cached():
    """POST /analyze/single twice with same params — second has from_cache=True."""

def test_cache_disabled_skips_caching():
    """With cache.enabled=false, no files are written and from_cache is always False."""
```

---

## Notes

- The cache is file-based JSON, not a database. This keeps dependencies minimal and makes the cache trivially inspectable (just `cat` a file). For the expected scale (6 scenarios, ~50 entries max), this is sufficient.
- Cache files are written atomically (write to a temp file, then rename) to avoid serving partial writes if the server crashes mid-write.
- The `point-impact` endpoint is NOT cached — it's already fast (~50 ms) and the input space is continuous (any lat/lon), so cache hit rate would be near zero.
- The batch endpoint is NOT cached — batch requests are less likely to be repeated exactly, and the response can be large. Individual drone results within a batch benefit from the single-drone cache if they happen to match.
- The 5-minute Streamlit `@st.cache_data` TTL in the dashboard remains as-is. It prevents redundant API calls during a single dashboard session. F24's cache prevents redundant computation across sessions and server restarts.
- If the `data/cache/` directory doesn't exist, `ResultCache.__init__` creates it. If the `data/` directory itself doesn't exist (e.g., in CI), caching silently disables itself (log a warning, set `result_cache = None`).
