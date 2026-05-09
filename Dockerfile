FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gcc g++ libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN mkdir -p src/droneimpact && touch src/droneimpact/__init__.py
RUN pip install --no-cache-dir .

COPY src/ ./src/
RUN pip install --no-cache-dir . --no-deps

COPY config.yaml .

RUN python -c "from droneimpact.physics.warmup import warmup_jit; warmup_jit()"

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=3 --start-period=60s \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "droneimpact.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
