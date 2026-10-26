# One image for every DraftPilot service; the command picks the role:
#   draftpilot serve | worker | migrate | mcp --http | rag
#
#   docker build -t draftpilot .                 # runtime image (installed wheels, non-root)
#   docker build --target dev -t draftpilot-dev . # source tree + uv, for compose.dev.yml

# --- the React studio -------------------------------------------------------------------------
FROM node:22-alpine AS studio
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- development: the source tree, installed editable (compose.dev.yml mounts src/ over it) ----
FROM python:3.13-slim AS dev
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY . /app
COPY --from=studio /frontend/dist /app/frontend/dist
ARG INSTALL_DEBUGPY=false
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --all-packages --no-dev \
    $( [ "${INSTALL_DEBUGPY}" = "true" ] && printf '%s' "--group debugpy" )
ENV PATH="/app/.venv/bin:${PATH}"
EXPOSE 8000
ENTRYPOINT ["draftpilot"]
CMD ["serve"]

# --- wheels: draftpilot (with the studio inside) and draftpilot-mcp ---------------------------
FROM dev AS wheels
RUN rm -rf src/draftpilot/studio && cp -R frontend/dist src/draftpilot/studio \
    && uv build --all-packages --wheel --out-dir /wheels \
    && uv export --frozen --all-packages --no-dev --no-emit-workspace --no-hashes -o /wheels/requirements.txt

# --- runtime: the published image --------------------------------------------------------------
FROM python:3.13-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /bin/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 VIRTUAL_ENV=/opt/draftpilot PATH="/opt/draftpilot/bin:${PATH}"
RUN --mount=type=bind,from=wheels,source=/wheels,target=/wheels --mount=type=cache,target=/root/.cache/uv \
    uv venv /opt/draftpilot \
    && uv pip install -r /wheels/requirements.txt \
    && uv pip install --no-deps /wheels/*.whl
RUN useradd --create-home --uid 10001 draftpilot && mkdir -p /data/backups && chown -R draftpilot /data
USER draftpilot
WORKDIR /home/draftpilot
# The production web process refuses to start without the studio build.
ENV WEB__REQUIRE_FRONTEND=true BACKUP__ROOT=/data/backups
EXPOSE 8000
LABEL org.opencontainers.image.source="https://github.com/amruthvvkp/DraftPilot" \
      org.opencontainers.image.description="DraftPilot: agentic screenplay studio (web, worker, MCP, RAG)" \
      org.opencontainers.image.licenses="MIT"
ENTRYPOINT ["draftpilot"]
CMD ["serve"]
