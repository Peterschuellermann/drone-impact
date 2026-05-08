# F18 — Docker Compose Deployment

**Status:** pending  
**Branch:** `feature/F18-docker-compose`  
**Dependencies:** F15

---

## Goal

Provide a single `docker compose up` command that starts the full DroneImpact stack: the FastAPI analysis API and the Streamlit dashboard. The dashboard is pre-configured to talk to the API service by container name. Data files are shared via a volume mount.

---

## Acceptance Criteria

- [ ] `docker-compose.yml` at project root defines two services: `api` and `dashboard`
- [ ] `docker compose up` starts both services without manual configuration
- [ ] API service is reachable at `http://localhost:8000` from the host
- [ ] Dashboard service is reachable at `http://localhost:8501` from the host
- [ ] Dashboard calls the API via internal Docker network (`http://api:8000`), not localhost
- [ ] `data/` directory is mounted as a shared volume so both services access the same data files
- [ ] `config.yaml` is mounted into both containers
- [ ] Environment variables can override config values (e.g., `DRONEIMPACT_MC_SAMPLES`)
- [ ] `docker compose up --build` rebuilds both images from clean state
- [ ] Health check: API service has a health check using `GET /health`; dashboard depends on API being healthy
- [ ] `docker compose down` cleanly stops both services
- [ ] Both images are based on `python:3.11-slim` for consistency
- [ ] Total image size for both services combined < 2 GB

---

## Implementation Steps

### 1. Dashboard Dockerfile

Create `Dockerfile.dashboard` at project root:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir -e ".[dashboard]"
EXPOSE 8501
CMD ["streamlit", "run", "src/droneimpact/dashboard/app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
```

- Uses the `dashboard` optional dependency group from `pyproject.toml` (added in F15)
- `--server.headless=true` suppresses the browser-open prompt in containers

### 2. Update existing Dockerfile

Rename the existing `Dockerfile` to `Dockerfile.api` (or keep as `Dockerfile` and reference it explicitly in compose). Ensure it:

- Exposes port 8000 (currently uses 8080 — update to 8000 for consistency with the spec)
- Copies `config.yaml` as a default (overridden by volume mount)
- Has a `HEALTHCHECK` instruction: `HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1`

### 3. Docker Compose file

Create `docker-compose.yml`:

```yaml
services:
  api:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data:ro
      - ./config.yaml:/app/config.yaml:ro
    environment:
      - DRONEIMPACT_HOST=0.0.0.0
      - DRONEIMPACT_PORT=8000
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 60s

  dashboard:
    build:
      context: .
      dockerfile: Dockerfile.dashboard
    ports:
      - "8501:8501"
    volumes:
      - ./data:/app/data:ro
      - ./config.yaml:/app/config.yaml:ro
    environment:
      - DRONEIMPACT_API_URL=http://api:8000
    depends_on:
      api:
        condition: service_healthy
```

Key decisions:
- `data/` mounted read-only — containers don't write to data files
- `start_period: 60s` on API health check — startup loads DEM, Kontur, and OSM data which can take up to 60s
- Dashboard waits for API to be healthy before starting
- `DRONEIMPACT_API_URL` environment variable tells the dashboard where the API lives

### 4. Dashboard API URL configuration

Update `src/droneimpact/dashboard/utils.py` (from F15) to read the API endpoint from:

1. `DRONEIMPACT_API_URL` environment variable (set by Docker Compose)
2. `config.yaml` → `dashboard.api_endpoint` (for local development)
3. Default: `http://localhost:8000`

This requires no changes to the dashboard code beyond reading `os.environ.get("DRONEIMPACT_API_URL")` as the first priority.

### 5. API port alignment

Update the existing `Dockerfile` to use port 8000 instead of 8080:

- Change `EXPOSE 8080` → `EXPOSE 8000`
- Change uvicorn `--port 8080` → `--port 8000`

Update the startup command to respect `DRONEIMPACT_PORT` environment variable if set.

### 6. .dockerignore

Create `.dockerignore` (or update if it exists):

```
.git
__pycache__
*.pyc
.pytest_cache
tests/
docs/
plans/
spec/
*.md
.env
data/
```

`data/` is excluded from the build context (mounted at runtime). `tests/` excluded to reduce image size.

### 7. Testing

- `tests/integration/test_docker_compose.py`: skipped by default (requires Docker), enabled with `--run-docker` flag
  - `docker compose up -d --build`
  - Wait for health check to pass
  - `POST http://localhost:8000/analyze/single` with a test payload → assert 200
  - `GET http://localhost:8501` → assert 200 (Streamlit serves HTML)
  - `docker compose down`
- Manual verification checklist (documented in plan, not automated):
  - [ ] Dashboard can call API and display results
  - [ ] Stopping API shows graceful degradation in dashboard
  - [ ] `docker compose logs` shows both services
  - [ ] Rebuilding with `--build` picks up code changes

---

## Notes

- The API currently uses port 8080 in the Dockerfile but the spec and all docs reference 8000. This plan aligns on 8000.
- `curl` must be available in the API container for the health check. `python:3.11-slim` includes it. If not, add `RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*`.
- Data files are large (DEM ~4 GB, Kontur ~500 MB). They are mounted, not copied, to keep image sizes small.
- For production deployments beyond Docker Compose (Kubernetes, ECS), this plan provides the base images. Orchestration manifests are out of scope.
