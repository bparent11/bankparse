# Build from the repository root: docker build -f apps/api/Dockerfile .
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.16 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv

# Workspace metadata first for better layer caching.
COPY pyproject.toml uv.lock ./
COPY packages/bankparse/pyproject.toml packages/bankparse/README.md packages/bankparse/LICENSE packages/bankparse/
COPY apps/api/pyproject.toml apps/api/
COPY packages/bankparse/src packages/bankparse/src
COPY apps/api/src apps/api/src

RUN uv sync --frozen --no-dev --package bankparse-api

ENV PATH="/opt/venv/bin:$PATH" BANKPARSE_DATA_DIR=/data
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "bankparse_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
