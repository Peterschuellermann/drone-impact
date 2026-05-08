FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY config.yaml .
COPY src/ ./src/

CMD ["uvicorn", "droneimpact.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
