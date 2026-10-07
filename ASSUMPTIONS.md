# Assumptions and decisions

Decisions made where the spec (`docs/LeadScout_Spec_v2.pdf`) is ambiguous or silent.
Each entry names the requirement it relates to. Product owner: please confirm or correct.

## Recorded during M0 / M1

| # | Spec ref | Decision |
|---|---|---|
| A1 | 5 | Stack: Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, PostgreSQL, Redis + RQ; uv for packaging. SQLite is supported for local tests only. |
| A2 | 3.1.3 | Deployment topology Option A (deterministic orchestrator). The LLM is used only for classification, summarising and drafting. |
| A3 | 6.1 | Primary keys are UUIDs (stable ids for Sheets upsert in M9). List fields (`target_roles`, `categories`, `reasons`, `sources`) are JSON (JSONB on Postgres) for portability. Enums are VARCHAR + CHECK constraints rather than native Postgres enums, to keep migrations simple. |
| A4 | 6.1 | Fields added beyond the spec: `Business.domain` (normalised, for FR-5 de-dupe), `Business.phone`, `Business.sources` (merged sources, AC-3), `Contact.status` (export `status` column; the spec lists it in 6.2 but not on any entity), timestamps on most tables. |
| A5 | 6.2 / FR-22 | Export is **one row per contact**. Businesses without contacts are not exported. Default filter is lead status `qualified`. |
| A6 | 6.2 vs FR-24 | Spec 6.2 says "email blank if suppressed"; FR-24 says "exclude suppressed contacts". Implemented the stricter FR-24: contacts whose email or email domain is on the suppression list, or whose status is `opted_out`, are omitted entirely. |
| A7 | 6.2 / AC-12 | **Conflict:** phones must be E.164 (start with `+`), but cells starting with `+` must be apostrophe-prefixed. Resolution: in the `phone` column only, values matching strict E.164 (`^\+[1-9]\d{1,14}$`) are left intact (digits only, no payload possible). Everything else starting with `= + - @`, plus TAB / CR (OWASP), is prefixed with `'`. |
| A8 | 6.2 / FR-13 / FR-15 | Email is exported only when `email_status` is `valid` or `risky`. `inferred` requires the per-export opt-in `include_inferred=true` (AC-8). `unverified` and `invalid` are blank (AC-5). Phone is exported only when `phone_status` is `valid` (blank if unverified or do-not-call). |
| A9 | 6.2 | `posts_this_year` = the highest `posts_ytd` across the business's channels ("any channel"), or `unknown` if none. Channel-selection rules (any / all / specific) arrive with the M2 qualification engine. |
| A10 | 6.2 | `retrieved_at` is exported as an ISO 8601 date (`YYYY-MM-DD`). `industry` comes from the campaign. `qualification_reason` is the score reasons joined by `"; "`. |
| A11 | NFR-4, CR-10 | Field-level encryption of contact data and audit-log immutability are deferred to M6 / M10. The tables exist now. |

## Recorded during M2

| # | Spec ref | Decision |
|---|---|---|
| Q1 | 4.2, MCP-5 (R1) | Two scoring stages. `pre_lookup` (no contact search yet) sets `lookup_eligible`: establishment, location/website, low activity and not-excluded must all **pass**, and free-signal points must meet the qualified threshold scaled to the free-signal weights (60 × 65/100 = 39 by default). A pre-lookup lead is `review` (or `rejected`), never `qualified`. `final` applies once `Business.contact_search_at` is set. |
| Q2 | 4.1, AC-2 (R2) | Unknown activity forces `review` at any score. It is not lookup-eligible, so no credits are spent until activity is entered or overridden. |
| Q3 | AC-4, 4 | Hard rejects (status `rejected` at any score): company dissolved, domain on the suppression list, existing customer (`existing_customer_domains`), and chain/franchise when `exclude_chains` (default **true**, open question in 13). |
| Q4 | 4 | Established = active company incorporated ≥ 2 y, OR domain age ≥ 2 y, OR ≥ 20 reviews. With no data at all the result is `unknown`, which scores 0 and blocks lookup. |
| Q5 | 4 | Location/website passes on a live website (`website_live`, set by the M4 fetcher) or a verified address. A website URL that hasn't been checked yet counts as `unknown`. |
| Q6 | 4 | Low-activity channel mode defaults to `all` (every channel with data this year is below N). `any` = at least one channel; `specific` = every listed channel has data and is below N. Only signals dated in the current calendar year count, using the latest signal per channel. |
| Q7 | 4.3 | Fit-to-industry: any category contains a keyword. Keywords come from `industry_keywords`, or default to the campaign industry's words with plurals stripped. Fit is scored but does not gate lookup. |
| Q8 | 4.3 | Contactable = at least one contact with a `valid` email or `valid` phone (`risky` does not count). Decision maker = any contact title matching the expanded target roles (MCP-11, `qualification/roles.py`). |
| Q9 | 4.3 / FR-2 | Score = round(earned / total weight × 100), so edited weights need not sum to 100. |
| Q10 | 4.3 | **Spec gap:** with default weights the free signals alone total 65, so a business with no decision maker found can still finish `qualified` (score 60–65). Kept per spec; export is per contact, so these leads produce no rows. Product owner: should `qualified` require a decision maker? |
| Q11 | FR-11 | Operator rule overrides (with audit log) are deferred to the M7 UI. Engine results already carry per-rule outcomes for this. |

## Raised during spec review (to be resolved in M2 / M6)

| # | Spec ref | Issue and proposed decision |
|---|---|---|
| R1 | 4.2, 4.3, MCP-5 | **Circular gate.** "Qualified" (score ≥ 60) includes decision-maker (20) and contactability (15), which need `person_search` / `person_lookup`, but lookups only run on qualified businesses. Proposal: define a separate *lookup-eligible* gate (all free-signal rules pass, and pre-lookup score ≥ threshold scaled to the available weights). The final Qualified / Review status is computed after enrichment. |
| R2 | 4.1, AC-2 | Unknown activity forces `review` status regardless of numeric score. |
| R3 | CR-4, AC-7 | `entity_type` usually only comes from Companies House. If it is `unknown`, the business is treated as a possible sole trader under UK jurisdiction, so cold email is blocked until a lawful basis is recorded. |
| R4 | FR-4, 3.1 | RocketReach `company_search` may not support radius filtering. If not, results are geocoded and filtered locally (confirm against the live tool schema in M3). |
