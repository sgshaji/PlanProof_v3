.PHONY: lint typecheck test test-reasoning verify-data evaluate all \
       docker-build docker-up docker-down docker-shell docker-lint docker-typecheck docker-test

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

typecheck:
	mypy src/

test:
	pytest --cov=planproof --cov-report=term-missing tests/

test-reasoning:
	pytest --cov=planproof.reasoning --cov-report=term-missing --cov-fail-under=90 tests/unit/reasoning/

verify-data:
	python -m planproof.evaluation.verify_data

evaluate:
	python -m planproof.evaluation.run_ablation

all: lint typecheck test

# --- Docker targets (run everything inside the dev container) ---

COMPOSE_DEV = docker compose -f docker/docker-compose.dev.yml
DEV_EXEC    = $(COMPOSE_DEV) exec planproof-dev

docker-build:
	$(COMPOSE_DEV) build

docker-up:
	$(COMPOSE_DEV) up -d

docker-down:
	$(COMPOSE_DEV) down

docker-shell:
	$(DEV_EXEC) bash

docker-lint:
	$(DEV_EXEC) make lint

docker-typecheck:
	$(DEV_EXEC) make typecheck

docker-test:
	$(DEV_EXEC) make test

docker-all:
	$(DEV_EXEC) make all
