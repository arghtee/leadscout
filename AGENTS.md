# Agent guide

Spec: `docs/LeadScout_Spec_v2.pdf`. Work one milestone (Section 11) at a time. Record ambiguities in `ASSUMPTIONS.md`.

## Commands
- Install: `uv sync`
- Lint/format: `uv run ruff check . && uv run ruff format --check .`
- Types: `uv run mypy` (strict)
- Tests: `uv run pytest --cov --cov-fail-under=80` (SQLite). Against Postgres: `TEST_DATABASE_URL=postgresql+psycopg://leadscout:leadscout@localhost:5432/leadscout uv run pytest`
- New migration: `DATABASE_URL=<postgres url> uv run alembic revision --autogenerate -m "..."`. Then **delete duplicate `sa.CheckConstraint(..., name="<enum_name>")` lines** that Alembic emits for enums (keep the `op.f("ck_...")` ones), and set `create_constraint=False` on `sa.Enum` in the migration. `tests/test_migrations.py` fails on model/migration drift.
- Full stack: `docker compose up --build`

## Rules
- Never implement anything in spec Section 3.3 (no LinkedIn/Facebook/Instagram scraping).
- All company/contact data goes through the RocketReach MCP wrapper (M3+). Never call credit-spending tools in tests; use fixtures and the mock server.
- No contact data in logs.
