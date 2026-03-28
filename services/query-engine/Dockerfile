FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

FROM base AS builder

RUN pip install --no-cache-dir poetry==2.3.2 && \
    poetry config virtualenvs.in-project true

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root --no-interaction

COPY . .
RUN poetry install --only main --no-root --no-interaction

FROM base AS runtime

RUN addgroup --system appgrp && adduser --system --ingroup appgrp appuser

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/app /app/app

ENV PATH="/app/.venv/bin:$PATH"

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
