FROM python:3.13-slim

# Predictable, log-friendly Python in a container -- same base image and env flags as the
# legacy Dockerfile (repo root), kept consistent rather than inventing a second convention.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --uid 1000 appuser

# The API is read-only against a DuckDB file built elsewhere (`make dbt-build`) -- it is
# never baked into the image. Mount it at runtime, e.g.:
#   docker build -f api/Dockerfile -t bridge-api .
#   docker run -v $(pwd)/bridge.duckdb:/app/bridge.duckdb:ro -p 8000:8000 bridge-api
COPY api/ api/
COPY config.py ./

USER appuser

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
