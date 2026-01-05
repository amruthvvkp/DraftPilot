# For more information, please refer to https://aka.ms/vscode-docker-python
FROM python:3.13-slim

EXPOSE 8000

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

ENV UV_LINK_MODE=copy

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Set venv location outside mounted directory to prevent overwrite
# This allows bind mounting ./:/app without affecting the virtual environment
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app
COPY . /app

RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-cache
