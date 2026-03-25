.PHONY: install lint typecheck test test-reasoning verify-data evaluate all

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
