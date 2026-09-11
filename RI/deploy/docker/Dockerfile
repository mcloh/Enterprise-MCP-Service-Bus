# Shared image for every RI service (Gateway, example MCP servers, ...).
# docker-compose.yml selects the process to run per service via `command:`.
#
# NOTE: not verified with a real `docker build` in this session -- no Docker
# daemon was available in the sandbox this was authored in (see RI/README.md,
# "Validado nesta sessão" for exactly what *was* run). Please verify on first
# use in an environment with Docker and report back if anything needs fixing.
FROM python:3.12-slim AS base

WORKDIR /app

# System deps kept minimal on purpose -- this image has no compiled
# dependencies today; add build-essential here if that changes.
COPY pyproject.toml ./
COPY src ./src
COPY services ./services

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e .

# Runs as a non-root user; every RI service binds 0.0.0.0 inside its own
# container network namespace, never the host network directly.
RUN useradd --create-home --uid 10001 emcp
USER emcp

EXPOSE 8000 8100

# Overridden per-service by docker-compose.yml `command:`.
CMD ["python3", "-m", "emcp_bus.gateway.server"]
