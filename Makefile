.PHONY: install lint typecheck test test-reasoning verify-data evaluate all \
       services-up services-down services-status ollama-pull

# --- Local development (Python runs on host) ---

install:
	pip install -e ".[dev]"

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

# --- Backing services (Neo4j + Ollama via Docker) ---

COMPOSE = docker compose -f docker/docker-compose.yml

services-up:
	$(COMPOSE) up -d

services-down:
	$(COMPOSE) down

services-status:
	$(COMPOSE) ps

ollama-pull:
	docker exec planproof-ollama ollama pull llama3.1
