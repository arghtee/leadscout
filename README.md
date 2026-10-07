# LeadScout

Local business lead discovery, qualification and outreach assistant.
Built milestone-by-milestone from the spec in [`docs/LeadScout_Spec_v2.pdf`](docs/LeadScout_Spec_v2.pdf).
Decisions on ambiguous requirements are recorded in [`ASSUMPTIONS.md`](ASSUMPTIONS.md).

| Milestone | Status |
|---|---|
| M0 Project scaffold | done |
| M1 Data model + CSV export (AC-12) | done |
| M2 Qualification engine (AC-1, AC-2, AC-4) | done |
| M3–M10 | not started |

## Stack

Python 3.12 · FastAPI · SQLAlchemy 2 + Alembic · PostgreSQL (SQLite for local tests) · Redis + RQ ·
uv · ruff · mypy (strict) · pytest. Frontend (React + Vite) arrives in M7.

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up --build          # api on :8000, worker, postgres, redis; runs migrations
docker compose exec api python -m leadscout.seed --businesses 200
curl localhost:8000/health
curl localhost:8000/campaigns
curl -o leads.csv "localhost:8000/campaigns/<campaign_id>/export.csv"
```

OpenAPI docs: <http://localhost:8000/docs>.

## Local development (no Docker)

Requires [uv](https://docs.astral.sh/uv/).

```bash
make install                 # uv sync (creates .venv with Python 3.12)
make migrate                 # alembic upgrade head (DATABASE_URL, default sqlite:///./leadscout.db)
make seed                    # 200 fake businesses
make run                     # uvicorn on :8000 with reload
make check                   # lint + format check + mypy + tests with coverage
```

## CSV export

`GET /campaigns/{id}/export.csv`

| Query param | Default | Meaning |
|---|---|---|
| `mode` | `full` | `full` (15 columns, spec 6.2) or `minimum` (name, role, phone, email) |
| `bom` | `false` | Prefix UTF-8 BOM for Excel |
| `status` | `qualified` | Lead status filter, repeatable (`qualified`, `review`, `rejected`) |
| `min_score` / `max_score` | – | Score range filter |
| `include_inferred` | `false` | Include `inferred` (pattern-guessed) emails (FR-15 / AC-8 opt-in) |

Rules: one row per contact; RFC 4180 quoting with CRLF; ISO 8601 dates; suppressed or opted-out
contacts are excluded; emails exported only when `valid`/`risky`, phones only when `valid`;
cells starting with `= + - @ TAB CR` are prefixed with `'` to block CSV/formula injection (AC-12).

## Qualification (M2)

Rules and scoring are pure functions in `qualification/engine.py`, configured per campaign
(`Campaign.rules_json`, validated by `QualificationRules`).

| Endpoint | Purpose |
|---|---|
| `GET /campaigns/{id}/rules` | Current rules, with defaults filled in |
| `PUT /campaigns/{id}/rules` | Replace rules (N posts, channel mode, min age/reviews, weights, thresholds, exclusions) |
| `POST /campaigns/{id}/qualify` | Re-score every business; returns counts by status |

Scoring runs in two stages (ASSUMPTIONS R1/R2):
- **pre_lookup** (free signals only): sets `lookup_eligible`, which gates paid contact lookups. Leads at this stage are never "qualified".
- **final** (after contact search): decision maker and contactability are added to the score.

Dissolved companies, suppressed domains, existing customers and (by default) chains are rejected.
Unknown activity always goes to review. Each `LeadScore` stores `reasons` plus per-rule
`rule_results` with points and evidence.

## Layout

```
src/leadscout/
  api/main.py           FastAPI app: /health, /campaigns, rules, qualify, CSV export
  models.py, enums.py   Section 6.1 entities
  export/csv_export.py  Section 6.2 export
  qualification/        Section 4 rules config, role matching, engine, DB service
  seed.py               Fake data generator
  worker.py             RQ worker entry point
migrations/             Alembic migrations
tests/                  pytest suite (runs on SQLite or Postgres via DATABASE_URL)
```
