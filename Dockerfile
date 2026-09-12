# Single image for both the API and the mock store; the compose `command` picks which runs.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src:/app

WORKDIR /app

# uv resolves and installs far faster than pip, and is what we use locally too.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Dependency layer first so source edits do not invalidate the install.
COPY pyproject.toml README.md ./
COPY src/pricepilot/__init__.py src/pricepilot/__init__.py
RUN uv pip install --system --no-cache .

COPY src/ src/
COPY services/ services/
COPY alembic/ alembic/
COPY alembic.ini ./

# Non-root, because this image also runs on the VPS in Phase 7.
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

EXPOSE 8000 8001
CMD ["uvicorn", "pricepilot.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
