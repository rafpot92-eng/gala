# AGENTS.md — Meczyki Editorial Platform

## What this is

AI-assisted sports editorial platform. Databricks ingests articles from Meczyki, generates embeddings, retrieves context, and drafts editorials. FastAPI serves the API, Next.js serves the UI. Humans review and publish.

## Commands

```bash
make setup          # install backend + frontend deps
make db-init        # run database/001_schema.sql + 002_indexes.sql (+ seed in dev)
make dev            # start both backend and frontend
make backend        # backend only: uvicorn app.main:app --reload --port 8000
make frontend       # frontend only: cd frontend && npm run dev
make test           # backend pytest + frontend production build
```

Single backend tests: `uv run --directory backend python -m pytest`
Frontend build check: `cd frontend && npm run build`
Frontend lint: `cd frontend && npm run lint`

## Project layout

- `backend/` — FastAPI app (psycopg3, pydantic-settings, authlib, PyJWT) — deps in root `pyproject.toml`, managed with `uv`
- `frontend/` — Next.js 15 / React 19 / TypeScript app
- `databricks/` — notebooks (01_ingest, 02_embed, 03_editorial_agent, 04_search) + job YAMLs + `src/` business logic + ops scripts (`setup_secrets.py`)
- `database/` — SQL schema, indexes, seed data (run in order: 001 → 002 → 003)
- `config/` — environment YAML files (development.yml, staging.yml, production.yml)
- `scripts/` — shell scripts wrapping common tasks
- `src/gala/` — package placeholder (not yet populated)
- `pyproject.toml` — single source for backend deps (`uv sync` creates root `.venv`)

## Critical workflow rules

**AI agent must never set article status to `approved` or `published`.** The agent only creates `draft` status articles. Human editors move articles through the workflow:

```
draft → ready_for_review → approved → published
```

Transitions: `ready_for_review` can reject back to `draft`. Only `publisher` role can publish.

## Auth

Databricks OIDC → FastAPI callback → session cookie (`meczyki_session`, httponly). No JWT in localStorage. New users default to `viewer` role — do not auto-grant `editor`.

## Environment

Copy `.env.example` to `.env`. Key vars: `DATABASE_URL`, `JWT_SECRET`, `DATABRICKS_WORKSPACE_URL`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`. Frontend needs `.env.local` with `NEXT_PUBLIC_API_URL=http://localhost:8000`.

## Gotchas

- `scripts/dev.sh` re-runs full setup (uv sync + npm install) every time — use `make dev` or start backend/frontend manually
- Backend reads `.env` from project root via pydantic-settings
- Frontend connects to backend via `NEXT_PUBLIC_API_URL` — set this or it defaults to localhost:8000
- `scripts/test.sh` runs both backend tests AND frontend production build
- Databricks deploy uses bundle targets: `validate` → `deploy` → `prod`
