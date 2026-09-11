.PHONY: venv install lint format typecheck test dev up down logs validate-schemas

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
	$(VENV)/bin/mypy src services tests

test:
	$(VENV)/bin/python3 -m pytest

validate-schemas:
	# Placeholder until EP-02/EP-04 introduce the first JSON Schema-backed
	# YAML config types; will validate every file under config/ against its
	# schema (see docs/RI-PLANNING.md, EP-00-T03).
	@echo "No schema-validated config types yet (see EP-02-T01, EP-04-T01)."

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
