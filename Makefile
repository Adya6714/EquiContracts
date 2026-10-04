.PHONY: install up down migrate reset rules lint fmt typecheck test verify dev worker eval-extraction

PYTHON ?= .venv/bin/python

install:
	python3 -m venv .venv
	$(PYTHON) -m pip install -r apps/api/requirements-dev.txt
	npm --prefix apps/web install

# --- Infrastructure ---

up:
	docker compose up -d
	@echo "Waiting for services..."
	@docker compose exec postgres pg_isready -U postgres > /dev/null 2>&1 && echo "Postgres ready" || echo "Postgres not ready"

down:
	docker compose down

# --- Database ---

migrate:
	@docker compose exec -T postgres sh /docker-entrypoint-initdb.d/00-app-role.sh
	@for f in $$(ls packages/db/migrations/*.sql | sort); do \
		echo "Applying $$f..."; \
		docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d equicontracts -f /dev/stdin < "$$f"; \
	done

reset:
	docker compose exec -T postgres psql -U postgres -c "DROP DATABASE IF EXISTS equicontracts WITH (FORCE);"
	docker compose exec -T postgres psql -U postgres -c "CREATE DATABASE equicontracts;"
	$(MAKE) migrate
	@if [ -f packages/db/seed/dev_seed.sql ]; then \
		docker compose exec -T postgres psql -U postgres -d equicontracts -f /dev/stdin < packages/db/seed/dev_seed.sql; \
	fi

# --- Quality ---

rules:
	$(PYTHON) scripts/check_agent_rules.py

lint:
	$(PYTHON) -m ruff check --config apps/api/pyproject.toml apps/ packages/
	$(PYTHON) -m ruff format --check --config apps/api/pyproject.toml apps/ packages/
	npm --prefix apps/web run lint

fmt:
	$(PYTHON) -m ruff format --config apps/api/pyproject.toml apps/ packages/

typecheck:
	$(PYTHON) -m mypy --config-file apps/api/pyproject.toml apps/api/app/
	npm --prefix apps/web run typecheck

test:
	$(PYTHON) -m pytest -c apps/api/pyproject.toml \
		apps/api/tests/ packages/extraction/tests/ -v

verify: rules lint typecheck test
	@echo "All checks passed."

# --- Development ---

worker:
	PYTHONPATH=. $(PYTHON) -m apps.api.app.workers

eval-extraction:
	set -a; [ -f .env ] && . ./.env; set +a; \
	PYTHONPATH=. $(PYTHON) -m packages.extraction.eval_extraction_cli

dev:
	@$(PYTHON) -m uvicorn apps.api.app.main:app --reload --port 8000 & \
		api_pid=$$!; \
		npm --prefix apps/web run dev & \
		web_pid=$$!; \
		trap 'kill $$api_pid $$web_pid' EXIT INT TERM; \
		wait
