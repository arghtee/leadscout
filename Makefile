.PHONY: install lint format typecheck test check migrate seed run up down

install:
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy

test:
	uv run pytest --cov --cov-report=term-missing --cov-fail-under=80

check: lint typecheck test

migrate:
	uv run alembic upgrade head

seed:
	uv run python -m leadscout.seed --businesses 200

run:
	uv run uvicorn leadscout.api.main:app --reload --port 8000

up:
	docker compose up --build

down:
	docker compose down
