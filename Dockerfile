FROM python:3.11-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ && rm -rf /var/lib/apt/lists/*

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
ENV HOME=/tmp

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

COPY . .
RUN chown -R appuser:appgroup /app /tmp/.cache
USER appuser

CMD ["uv", "run", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
