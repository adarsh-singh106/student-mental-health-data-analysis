# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Recipe for this project's image. Steps mirror what you'd do by hand on a
# fresh laptop: get Python -> get uv -> install libraries -> copy code -> say
# what runs by default.
#
# Data (data/raw/) and the trained model (artifacts/) are NOT baked in. They
# are mounted from the host at run time (see Makefile / README), so the image
# stays code-only and the unlicensed CSV is never redistributed inside it.
# ---------------------------------------------------------------------------

# Step 1 — start from a box that already has Python 3.10.
# "-slim" is a smaller variant: same Python, fewer extra OS packages we don't need.
FROM python:3.10-slim

# Step 2 — get uv (our package manager). Instead of installing it ourselves,
# we copy the ready-made uv binary out of uv's official image. Pinned to an
# exact version so the build is reproducible (not "whatever latest is today").
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv

# All following commands run inside this folder in the image.
WORKDIR /app

# Step 3 — install libraries FIRST, before copying our code.
# Why copy only these two files first? Docker caches each step. As long as
# pyproject.toml + uv.lock don't change, Docker reuses the installed-libraries
# layer and skips re-installing on every code edit. Big speed win.
COPY pyproject.toml uv.lock ./

# --frozen: obey uv.lock exactly, don't re-resolve versions.
# --no-install-project: install only the dependencies now, not our own package
#   (our code isn't copied yet). We install the project itself in the next step.
RUN uv sync --frozen --no-install-project

# Step 4 — now copy our actual source code into the box.
# tests/ is copied too so `make test` (and CI in 0.7) can run inside the image.
# README.md is required here because pyproject's `readme = "README.md"` makes
# hatchling read it when the full `uv sync` below installs our own package.
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY tests/ ./tests/
COPY README.md ./

# Install our own package now that the code is present.
RUN uv sync --frozen

# uv installs into a virtual env at /app/.venv. Putting its bin on PATH means
# we can call "uvicorn"/"python" directly without the "uv run" prefix.
ENV PATH="/app/.venv/bin:$PATH"

# Step 5 — default command when the container starts: serve the API.
# 0.0.0.0 (not 127.0.0.1) so the server is reachable from outside the container.
# The Makefile overrides this command for training.
EXPOSE 8000
CMD ["uvicorn", "mental_health.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
