# DroneImpact — Development Workflow

## Task Tracking

All remaining tasks and feature plans are tracked as GitHub issues at https://github.com/Peterschuellermann/drone-impact/issues. Issues are labelled by milestone (`v1.1c`, `v1.2`, `v1.3`, `v1.4`) and category (`physics`, `dashboard`, `performance`).

**To pick up work:** check the GitHub issues for the next available task.

---

## Concurrency

Multiple agents and people work in this repository simultaneously. Follow these rules to avoid conflicts:

### Git Pull — Stay Up to Date

- **Always `git pull origin main` before starting any work** — at the beginning of a session, before creating a branch, and before merging.
- If you've been working for a while, pull again before merging to catch changes others have pushed.

### Branching — Never Commit Directly to Main

- **All work happens on branches**, never directly on `main`. This includes docs, spec changes, and fixes — not just features.
- Branch naming: `feature/<plan-id>-<short-name>`, `fix/<description>`, or `docs/<description>`.
- Merge to main via squash merge, then push.

### Git Worktrees

- Use `git worktree` so multiple branches can be worked on simultaneously without conflicts.
- Create a worktree for each branch: `git worktree add ../droneimpact-<plan-id> -b feature/<plan-id>-<short-name> main`
- After merging to main, remove the worktree: `git worktree remove ../droneimpact-<plan-id>`
- Never run `git checkout` in the main working directory — use worktrees instead.
- When using Claude Code's Agent tool, prefer `isolation: "worktree"` for implementation tasks.

---

## Feature Development Workflow

1. **Pull latest:** `git pull origin main`
2. **Pick an issue:** Check GitHub issues for the next available task.
3. **Worktree:** `git worktree add ../droneimpact-<id> -b feature/<id>-<short-name> main`
4. **Implement:** Work in the worktree. Make atomic commits as you go.
5. **Test:** Write unit and integration tests alongside or before code. All tests must pass before moving to the next step.
6. **Verify:** Run `pytest` — zero failures required before merging.
7. **Update spec:** If implementation differs from spec, update the relevant `/spec/` file.
8. **Pull again:** `git pull origin main` — catch any changes pushed while you were working.
9. **Merge:** From the main working directory: `git merge --squash feature/<id>-<short-name>` then commit with message `feat(<id>): <title>`.
10. **Push:** `git push origin main` — push immediately after the squash merge.
11. **Cleanup:** `git worktree remove ../droneimpact-<id>` and `git branch -d feature/<id>-<short-name>`.

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
