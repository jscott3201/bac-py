FROM python:3.13-alpine AS base

# Install uv from official distroless image (recommended by uv docs)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Build deps for orjson musl wheel compilation fallback
RUN apk add --no-cache gcc musl-dev

# Improve startup performance and ensure correct link mode
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Layer 1: dependency metadata (changes rarely)
COPY pyproject.toml uv.lock ./

# Layer 2: install deps including orjson via serialization extra
RUN uv sync --frozen --group test --extra serialization --no-install-project

# Layer 3: source code (changes frequently)
COPY src/ src/

# Install the project itself
RUN uv sync --frozen --group test --extra serialization

# Remove build deps to keep image lean
RUN apk del gcc musl-dev

# Layer 4: docker test infrastructure
COPY docker/ docker/

ENTRYPOINT ["uv", "run", "python", "docker/entrypoint.py"]
