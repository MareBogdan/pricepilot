# Lean SERVING image (ADR-0051): the read-only dashboard + API only. It is what Render builds
# (ADR-0052; Hugging Face Docker Spaces went paid). It deliberately has no torch / transformers / onnxruntime /
# sentence-transformers and no model file: the dashboard reads Neon + committed result files and
# never runs the matcher, embeddings or RAG at request time. The mock store (compose) reuses it.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src:/app

WORKDIR /app

# uv resolves and installs far faster than pip, and is what we use locally too.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Dependency layer first so source edits do not invalidate the install. `-r pyproject.toml`
# installs [project.dependencies] only (the lean core), not the `pipeline` / `dev` extras, and
# not the package itself: the code runs from PYTHONPATH, so config/ and docs/ paths (resolved
# relative to the source tree) stay valid.
COPY pyproject.toml ./
RUN uv pip install --system --no-cache -r pyproject.toml

COPY src/ src/
COPY services/ services/
# config/ = pricing-policy.toml (margin floor, read by the dashboard); the three JSONs are the only
# result files the dashboard reads (src/pricepilot/api/results.py) -- without them the headline
# tiles would show "n/a".
COPY config/ config/
COPY docs/learned/results/mmarco-mMiniLMv2-finetuned-ep6-metrics.json \
     docs/learned/results/mmarco-mMiniLMv2-zeroshot-metrics.json \
     docs/learned/results/phase5-policy-retrieval-eval.json \
     docs/learned/results/

# Non-root (uid 1000, also what Hugging Face Spaces would use).
RUN useradd --create-home --uid 1000 app && chown -R app:app /app
USER app

# Fail the BUILD (not the Space at runtime) if the app needs anything outside the core dependencies.
RUN python -c "import pricepilot.api.main, services.mock_store.app"

EXPOSE 7860 8000 8001
# Render injects PORT and expects the app on 0.0.0.0:$PORT; locally it falls back to 7860.
# Shell form so ${PORT:-7860} is expanded; `exec` keeps uvicorn as PID 1 so it gets SIGTERM.
CMD ["sh", "-c", "exec python -m uvicorn pricepilot.api.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
