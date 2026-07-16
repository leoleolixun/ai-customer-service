.PHONY: install lint typecheck test migrate openapi dev worker

install:
	uv sync --all-groups

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy app scripts examples tests

test:
	uv run pytest

migrate:
	uv run alembic upgrade head

openapi:
	uv run python scripts/export_openapi.py

dev:
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	uv run celery -A app.workers.celery_app worker --loglevel=INFO
