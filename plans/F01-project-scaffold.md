# F01 — Project Scaffold

**Status:** pending  
**Branch:** `feature/F01-project-scaffold`  
**Dependencies:** none

---

## Goal

Establish the complete project skeleton: Python package layout, dependency management, configuration loading, test infrastructure, and Docker container. Nothing in this plan computes physics or calls an API — it is purely structure and plumbing. Every subsequent plan builds on this foundation.

---

## Acceptance Criteria

- [ ] `pip install -e ".[dev]"` installs all dependencies without errors
- [ ] `pytest` discovers and runs (currently zero tests — that is fine; the runner must exit 0)
- [ ] `python -c "from droneimpact.config import load_config; load_config()"` loads `config.yaml` without error
- [ ] `docker build -t droneimpact .` completes without errors
- [ ] `docker run droneimpact python -c "from droneimpact.config import load_config; print('ok')"` prints `ok`
- [ ] `mypy src/` passes (zero errors; strict mode can be relaxed per-module in later plans)
- [ ] `ruff check src/` passes

---

## Implementation Steps

### 1. Directory structure

Create the following empty files and directories:

```
src/droneimpact/__init__.py
src/droneimpact/config.py
src/droneimpact/api/__init__.py
src/droneimpact/physics/__init__.py
src/droneimpact/casualty/__init__.py
src/droneimpact/scoring/__init__.py
src/droneimpact/data/__init__.py
tests/__init__.py
tests/unit/__init__.py
tests/integration/__init__.py
tests/performance/__init__.py
tests/fixtures/           (empty directory, keep with .gitkeep)
data/                     (empty directory, gitignored)
```

### 2. pyproject.toml

Use `pyproject.toml` for all project metadata. Key sections:

**`[project]`**
- `name = "droneimpact"`
- `version = "0.1.0"`
- `requires-python = ">=3.11"`
- `dependencies`: fastapi, uvicorn[standard], numpy, numba, scipy, pyproj, h3, shapely, rasterio, pyyaml, pydantic>=2, pydantic-settings

**`[project.optional-dependencies]`**
- `dev`: pytest, pytest-cov, pytest-asyncio, httpx, mypy, ruff, hypothesis

**`[tool.pytest.ini_options]`**
- `testpaths = ["tests"]`
- `asyncio_mode = "auto"`
- `markers`: define `"perf: mark test as performance benchmark (skipped by default)"` — skip unless `--run-perf` flag passed

**`[tool.ruff]`**
- `line-length = 100`
- `select = ["E", "F", "I"]`

**`[tool.mypy]`**
- `python_version = "3.11"`
- `strict = false`
- `ignore_missing_imports = true`

### 3. config.yaml

Create `config.yaml` at the project root. Contents exactly as specified in `/spec/architecture.md` under "Configuration". All values are the v1 defaults. Add a top-level `version: "1.0"` field.

### 4. src/droneimpact/config.py

Implement config loading with Pydantic v2 models. Structure:

```python
class PhysicsConfig(BaseModel):
    n_monte_carlo_samples: int
    evaluation_spacing_m: int
    shahed136: Shahed136Params

class Shahed136Params(BaseModel):
    mass_kg: float
    warhead_mass_kg: float
    cruise_speed_m_s: float
    glide_ratio: float
    drag_coeff_tumbling: float
    reference_area_m2: float

class EngagementConfig(BaseModel):
    p_kill: float
    mode_weights: ModeWeights

class ModeWeights(BaseModel):
    propulsion_loss: float
    loss_of_control: float
    break_apart: float

class CasualtyConfig(BaseModel):
    blast: BlastParams
    fragmentation: FragParams
    infrastructure: InfraParams

# ... (full nested model hierarchy matching config.yaml)

class AppConfig(BaseModel):
    version: str
    physics: PhysicsConfig
    engagement: EngagementConfig
    casualty: CasualtyConfig
    data: DataPaths

def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """Load and validate config from YAML file."""
    ...
```

`load_config` reads the YAML file and returns a validated `AppConfig`. Raises a descriptive `ValueError` if any required field is missing or out of range. Uses `@model_validator` to check that `mode_weights` sum to 1.0 (within float tolerance).

### 5. .gitignore

Add entries for:
- `data/` (large runtime data files)
- `__pycache__/`, `*.pyc`, `.mypy_cache/`, `.ruff_cache/`
- `.pytest_cache/`, `htmlcov/`, `.coverage`
- `dist/`, `*.egg-info/`
- `.env`

### 6. Dockerfile

Multi-stage build is not needed at this point. Single stage:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY config.yaml .
COPY src/ ./src/

CMD ["uvicorn", "droneimpact.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
```

Note: `droneimpact.main` does not exist yet — it will be created in F11/F12. The Dockerfile is valid structure now; the CMD will be updated when the API is wired up.

### 7. src/droneimpact/main.py (stub)

Create a minimal FastAPI app stub so Docker CMD doesn't fail at import time:

```python
from fastapi import FastAPI
app = FastAPI(title="DroneImpact", version="0.1.0")
```

This stub will be replaced in F11 (startup + health) and F12 (API endpoints).

---

## Tests

### tests/unit/test_config.py

- Load `config.yaml` and assert that the returned `AppConfig` has the correct types and values for a sample of fields (e.g. `config.physics.n_monte_carlo_samples == 10000`, `config.engagement.p_kill == 0.50`).
- Assert that `load_config` raises `ValueError` when given a YAML with a missing required field.
- Assert that `load_config` raises `ValueError` when `mode_weights` do not sum to 1.0.
- Use `tmp_path` fixture to write malformed YAML to a temp file — do not modify `config.yaml`.

---

## Notes

- Do not vendor or pin exact versions of transitive dependencies — let pip resolve within the constraints. Pin only direct dependencies with `>=` lower bounds, not `==` exact pins.
- Numba requires LLVM; the `python:3.11-slim` image must have it. If `numba` import fails in Docker, fall back to `python:3.11` (non-slim). Check this during implementation.
- `h3` on PyPI is the `h3-py` package but imported as `h3`. Use `h3>=3.7` in deps.
