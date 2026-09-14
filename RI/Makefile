.PHONY: venv install lint format typecheck test dev up down logs validate-schemas export-schemas

VENV := .venv
PYTHON := $(VENV)/bin/python3

venv:
	python3 -m venv $(VENV)

install: venv
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -e ".[dev]"

lint:
	$(VENV)/bin/ruff check .
	$(VENV)/bin/ruff format --check .

format:
	$(VENV)/bin/ruff format .
	$(VENV)/bin/ruff check --fix .

typecheck:
	$(VENV)/bin/mypy src services agents tests scripts

# --forked (pytest-forked): one process per test function -- resolves the
# e2e suite's previously-documented flakiness (RI/README.md), where several
# in-process ASGI server pairs sharing one Python process/event loop across
# many sequential tests intermittently failed. Verified: 119/119 (97 unit +
# 22 e2e) pass reliably with it; costs roughly +1min total on this machine.
test:
	$(VENV)/bin/python3 -m pytest --forked

validate-schemas:
	$(VENV)/bin/python3 scripts/validate_config.py

export-schemas:
	$(VENV)/bin/python3 scripts/export_schemas.py

# Runs both M0 services directly on the host (no Docker required) --
# handy for local development and for environments without a Docker daemon.
dev:
	$(VENV)/bin/python3 -m example_mcp_servers.sales_domain.server & \
	echo $$! > /tmp/emcp-sales.pid; \
	sleep 1; \
	$(VENV)/bin/python3 -m emcp_bus.gateway.server

up:
	docker compose --profile core up --build

down:
	docker compose --profile core down

logs:
	docker compose --profile core logs -f
