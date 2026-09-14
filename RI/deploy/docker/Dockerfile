# Shared image for every RI service (Gateway, example MCP servers, ...).
# docker-compose.yml selects the process to run per service via `command:`.
#
# Verified with a real `docker build`/`docker compose up` (RI/README.md, "O
# que foi validado com Docker") -- this image originally omitted `config ./config`
# below, which built fine but made the Gateway fail closed at startup
# (`ConfigError`: config/clients not found -- `load_yaml_models`, EP-01/EP-04),
# since the container never had client registrations/profiles to load.
FROM python:3.12-slim AS base

WORKDIR /app

# System deps kept minimal on purpose -- this image has no compiled
# dependencies today; add build-essential here if that changes.
COPY pyproject.toml ./
COPY src ./src
COPY services ./services
# The Gateway loads client registrations/profiles/backend-credential config
# from `config/` at startup (EP-01/EP-04/EP-07, GatewayConfig.config_dir).
COPY config ./config

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e ".[otlp]"

# Runs as a non-root user; every RI service binds 0.0.0.0 inside its own
# container network namespace, never the host network directly.
RUN useradd --create-home --uid 10001 emcp
USER emcp

EXPOSE 8000 8100 8101

# Overridden per-service by docker-compose.yml `command:`.
CMD ["python3", "-m", "emcp_bus.gateway.server"]
