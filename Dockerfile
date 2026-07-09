FROM python:3.13-slim

# Predictable, log-friendly Python in a container.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install deps first so the layer caches across code changes. psycopg[binary]
# ships libpq in the wheel, so the slim image needs no apt packages.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Run as a non-root user (least privilege — also sets up the M4 hardening habit).
RUN useradd --create-home --uid 1000 appuser

# Copy only what the pipeline needs at runtime (no tests, infra, venv, or .env).
COPY ingest/ ingest/
COPY transform/ transform/
COPY config.py db.py ./

USER appuser

CMD ["python", "-m", "ingest.pipeline"]
