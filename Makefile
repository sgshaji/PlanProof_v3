.PHONY: install lint typecheck test test-reasoning seal-data verify-data evaluate all

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

generate-data:
	python -m planproof.datagen.runner --seed 42

seal-data:
	python -m planproof.datagen.split
	python -m planproof.datagen.integrity

verify-data:
	python scripts/verify_dataset.py

evaluate:
	python -m planproof.evaluation.run_ablation

all: lint typecheck test
