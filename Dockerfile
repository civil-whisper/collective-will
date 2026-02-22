FROM python:3.11-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

COPY pyproject.toml ./
RUN uv sync --no-dev

COPY . .
RUN chown -R appuser:appgroup /app
USER appuser

CMD ["uv", "run", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
