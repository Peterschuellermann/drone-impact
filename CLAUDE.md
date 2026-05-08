# DroneImpact — Development Workflow

## Agent Roles

Two agent types operate in this repository:

**Planning Agent** — reads `/spec/roadmap.md` and the spec files, then writes feature plans in `/plans/`. Does not write implementation code or modify `src/`. When a new version is being planned, it reads the previous version's plans and spec to maintain continuity.

**Implementation Agent** — reads one `[ ] pending` plan from `/plans/README.md`, implements it fully, tests it, and commits it to a feature branch. Does not plan new features or modify other plans. If the plan contains an error, it updates the plan AND the relevant spec file, then continues.

---

## Feature Development Workflow

1. **Pick a plan:** Read `/plans/README.md`. Take the first `[ ] pending` plan whose dependencies are all `[x] done`.
2. **Branch:** `git checkout -b feature/<plan-id>-<short-name>` from `main`.
3. **Implement:** Follow the plan step by step. Make atomic commits as you go.
4. **Test:** Write unit and integration tests alongside or before code. All tests must pass before moving to the next step.
5. **Verify:** Run `pytest` — zero failures required before merging.
6. **Update spec:** If implementation differs from spec, update the relevant `/spec/` file.
7. **Mark done:** Update plan status in `/plans/README.md` from `[ ]` to `[x]`.
8. **Merge:** Squash the feature branch into one commit on `main`. Commit message: `feat(<id>): <plan title>`.
9. **Push:** `git push origin main` — push immediately after the squash merge.

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

## Plans

All feature plans live in `/plans/`. Each is a single markdown file.

**Plan status in README:**
- `[ ]` pending — not started
- `[~]` in progress — branch open, implementation underway
- `[x]` done — merged to main, tests pass

**To pick up work:** open `/plans/README.md`, find the first `[ ]` plan with all dependencies marked `[x]`, read the full plan file, implement it.

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
├── plans/                  # feature plans (planning agent writes here)
├── spec/                   # living system specification
├── data/                   # runtime data files — gitignored, populated separately
├── config.yaml             # default runtime configuration
├── pyproject.toml          # project metadata, deps, pytest config
├── Dockerfile
└── CLAUDE.md               # this file
```

---

## Data Files

Large runtime data files (`data/kontur_*.gpkg`, `data/*_dem.tif`, `data/*_infra.geojson`) are **gitignored**. Tests that require spatial data use small synthetic fixtures in `tests/fixtures/`. The implementation must degrade gracefully when data files are absent (log a warning, mark `/health` as `data_loaded: false`).

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
