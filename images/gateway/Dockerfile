# Heimdall gateway image: MCP tools and the model proxy on port 8080.
# Build from the repo root, because it needs core/ and the lockfile:
#   docker build -f images/gateway/Dockerfile .
FROM python:3.11-slim
# uv installs exactly what uv.lock pins.
COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR /app
# Dependencies first so code changes don't reinstall them.
# Only the gateway group: no pytest in the image.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups --group gateway --no-install-project
COPY core ./core

# The gateway holds the real keys; don't run it as root.
RUN useradd --system --no-create-home gateway
USER gateway
EXPOSE 8080
CMD ["python", "-m", "core.gateway"]
