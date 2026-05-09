# DroneImpact — Development Workflow

## Task Tracking

All remaining tasks and feature plans are tracked as GitHub issues at https://github.com/Peterschuellermann/drone-impact/issues. Issues are labelled by milestone (`1.1.0`, `1.2.0`, `1.3.0`, `1.4.0`) and category (`physics`, `dashboard`, `performance`). Versions follow [Semantic Versioning](https://semver.org/).

**To pick up work:** check the GitHub issues for the next available task.

---

## Concurrency

Multiple agents and people work in this repository simultaneously. Follow these rules to avoid conflicts:

### Branching Model

Two long-lived branches:

- **`main`** — production-ready code. Only updated by merging `develop` when ready to release, tagged with a semver version. No direct commits.
- **`develop`** — integration branch. All feature and fix work merges here first.

Branch types and flow:

| Type | Naming | Branches from | Merges into |
|---|---|---|---|
| Feature | `feature/<name>` | `develop` | `develop` |
| Fix | `fix/<name>` | `develop` | `develop` |
| Hotfix | `hotfix/<name>` | `main` | `main` (tagged) AND `develop` |

Rules:
- **Never commit directly to `main` or `develop`.** All work happens on short-lived branches.
- **Always use `--no-ff` merges** to preserve branch history.
- **Tag every merge into `main`** with the release version (e.g., `1.2.0`).
- **Pull before branching:** `git pull origin develop` (or `main` for hotfixes).
- If you've been working for a while, pull again before merging to catch changes others have pushed.

### Merging Safely (Multi-Agent)

Multiple agents work in worktrees simultaneously. To avoid blocking each other:

1. **Do all work in a worktree** — never commit on `main` or `develop` in the primary repo.
2. **Merge into `develop` from the worktree**, not from the primary working directory.
3. **Push `develop` to origin** immediately after merging.
4. **Other agents pull from remote** (`git pull origin develop`) to pick up changes — they never see uncommitted local state.

### Git Worktrees

- Use `git worktree` so multiple branches can be worked on simultaneously without conflicts.
- Create a worktree for each branch: `git worktree add ../droneimpact-<plan-id> -b feature/<plan-id>-<short-name> develop`
- After merging to develop, remove the worktree: `git worktree remove ../droneimpact-<plan-id>`
- Never run `git checkout` in the main working directory — use worktrees instead.
- When using Claude Code's Agent tool, prefer `isolation: "worktree"` for implementation tasks.

---

## Feature Development Workflow

1. **Pull latest:** `git pull origin develop`
2. **Pick an issue:** Check GitHub issues for the next available task.
3. **Worktree:** `git worktree add ../droneimpact-<id> -b feature/<id>-<short-name> develop`
4. **Implement:** Work in the worktree. Make atomic commits as you go.
5. **Test:** Write unit and integration tests alongside or before code. All tests must pass before moving to the next step.
6. **Verify:** Run `pytest` — zero failures required before merging.
7. **Update spec:** If implementation differs from spec, update the relevant `/spec/` file.
8. **Pull again:** `git pull origin develop` — catch any changes pushed while you were working.
9. **Merge:** From the main working directory: `git merge --no-ff feature/<id>-<short-name>` into `develop`.
10. **Push:** `git push origin develop` — push immediately after merge.
11. **Cleanup:** `git worktree remove ../droneimpact-<id>` and `git branch -d feature/<id>-<short-name>`.

## Promoting to Main

When `develop` is stable and ready for release:

1. `git checkout main && git pull origin main`
2. `git merge --no-ff develop`
3. `git tag <version>`
4. `git push origin main --tags`

## Hotfix Workflow

For urgent production fixes only:

1. **Branch:** `git worktree add ../droneimpact-hotfix -b hotfix/<name> main`
2. **Fix and test.**
3. **Merge to main:** `git checkout main && git merge --no-ff hotfix/<name>` then tag and push.
4. **Merge to develop:** `git checkout develop && git merge --no-ff hotfix/<name>` then push.
5. **Cleanup:** `git worktree remove ../droneimpact-hotfix && git branch -d hotfix/<name>`

---

## Commit Conventions

Use conventional commits. Prefix: `feat`, `fix`, `test`, `refactor`, `docs`, `chore`.

```
feat(F04): add M1 propulsion-loss Monte Carlo simulation

- Vectorised NumPy implementation, no Python loops
- σ_heading and glide_ratio drawn from config
- Returns (N, 2) ENU impact point array
```

Keep commit messages factual. Do not narrate intent — the diff shows what changed.

---

## Testing Rules

- **Never modify a test to make failing code pass.** Fix the code.
- **You may update tests** when a public interface changes intentionally (renamed field, changed units, removed parameter). Document the change in the spec.
- Unit tests: `tests/unit/` — isolated, no file I/O, no network. Use in-memory fixtures.
- Integration tests: `tests/integration/` — components working together; may read fixture data from `tests/fixtures/`.
- Performance tests: `tests/performance/` — assert latency budgets. Must pass: single drone < 500 ms, batch of 50 < 15 s.
- Run all: `pytest`
- Run only unit: `pytest tests/unit/`
- Run with coverage: `pytest --cov=src/droneimpact`

---

## Spec

The `/spec/` directory is the living design document. Keep it accurate:

- If behaviour changes, update the relevant spec file in the same commit.
- If you discover a spec error, fix it and note it in the commit message.
- The spec describes the **current system**, not aspirational behaviour.
- Do not delete spec content unless the feature it describes is fully removed.

---

## File Layout

```
droneimpact/
├── src/
│   └── droneimpact/        # main Python package
│       ├── api/            # FastAPI routers and Pydantic schemas
│       ├── physics/        # Monte Carlo terminal trajectory models
│       ├── casualty/       # blast, fragmentation, population models
│       ├── scoring/        # engagement score formula and explainability
│       ├── data/           # data loaders: DEM, Kontur, OSM
│       └── config.py       # YAML config loading and validation
├── tests/
│   ├── unit/               # isolated function-level tests
│   ├── integration/        # component interaction tests
│   ├── performance/        # latency budget assertions
│   └── fixtures/           # small synthetic data files for tests
├── spec/                   # living system specification
├── data/                   # runtime data files — gitignored, populated separately
├── config.yaml             # default runtime configuration
├── pyproject.toml          # project metadata, deps, pytest config
├── Dockerfile
└── CLAUDE.md               # this file
```

---

## Data Files

Large runtime data files (`data/kontur_*.gpkg`, `data/*_dem.tif`, `data/*_infra.geojson`) are **gitignored**. Run `./scripts/download_data.sh` to download and preprocess all data.

- `.worktreeinclude` lists `data/` so that data files are automatically copied into new worktrees.
- Tests that require spatial data use small synthetic fixtures in `tests/fixtures/`.
- The implementation must degrade gracefully when data files are absent (log a warning, mark `/health` as `data_loaded: false`).

---

## Configuration

All tunable parameters live in `config.yaml`. No physics constants, weights, or radii are hard-coded. The config schema is validated at startup using Pydantic. See `/spec/architecture.md` for the full config structure.

---

## Performance Budget

| Scenario | Limit |
|---|---|
| Single drone analysis | < 500 ms |
| Batch of 50 drones | < 15 s |
| Server memory footprint (with Ukraine data) | < 1 GB |
| Startup time | < 60 s |

Performance tests in `tests/performance/` assert these limits. They are skipped in CI by default (they require real data); run locally with `pytest tests/performance/ --run-perf`.
