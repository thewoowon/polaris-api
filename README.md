# Polaris API

AI-based VOC (app review) auto-classification + reply-generation API.
Frontend lives in a separate repo.

## Stack

- FastAPI + Pydantic v2 + SQLAlchemy 2.x (async)
- PostgreSQL (via `asyncpg` runtime, `psycopg` sync for Alembic)
- Poetry + Python 3.11
- Docker Compose for local DB

## Quick start

```bash
cp .env.example .env
# edit .env: set JWT_SECRET_KEY (use `python -c "import secrets; print(secrets.token_urlsafe(48))"`)

docker compose up -d db            # start postgres
poetry install                     # install deps
poetry run alembic upgrade head    # apply migrations (once models exist)
poetry run uvicorn app.main:app --reload
```

OpenAPI docs: http://localhost:8000/docs

## Layout

```
app/
  api/v1/        FastAPI routers
  core/          config, security (JWT)
  db/            Base + async/sync session setup
  models/        SQLAlchemy models (register in __init__.py)
  schemas/       Pydantic request/response schemas
  services/      business logic (classification, policy, generation, ...)
alembic/         migrations
```

See [../web/polaris/blueprint.md](../../web/polaris/blueprint.md) for the full design doc.
