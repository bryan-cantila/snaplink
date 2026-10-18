# SnapLink

[![License: devuvo Community](https://img.shields.io/badge/license-devuvo_Community-blue.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](app/main.py)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg)](docker-compose.yml)

![SnapLink logo](assets/logo.png)

*Created by devuvo*

A production-style **URL shortener REST API** built by hand with **FastAPI + PostgreSQL** — no no-code tools. JWT auth, 7-char base62 short codes (or your own custom codes), click tracking with privacy-first IP hashing, per-link stats, rate limiting, an optional Redis cache for redirects, and Alembic migrations. Bring your own database — nothing is hardcoded.

![Swagger UI](docs/swagger.png)
![Demo flow](docs/demo.png)

> **Design:** Cyberpunk / HUD · **Palette:** #11 Prompt Blue `0B132B` + AI Green `39FF88` (per the devuvo standing app-design rule — every app gets its own look).

## Architecture

```
                    +------------------+
  POST /api/links   |    FastAPI       |   JWT auth · slowapi 30/min
  (auth)  --------> |  app/routers/    |---> PostgreSQL (SQLAlchemy async)
                    |                  |        users / links / clicks
  GET /{code} ----> |  redirect        |---> Redis (optional cache, 1h TTL)
  (public, 307)     |  + click track   |      falls back to DB when down
                    +------------------+
  Alembic migrations · docker-compose (api + postgres + redis)
```

## Quick start (Docker — recommended)

```bash
cp .env.example .env
# put a real secret in .env:  python -c "import secrets; print(secrets.token_hex(32))"
export JWT_SECRET=$(grep JWT_SECRET .env | cut -d= -f2)
docker compose up --build
# API → http://localhost:8000   |   themed docs → http://localhost:8000/docs
```

## Quick start (local Python)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit DATABASE_URL + JWT_SECRET
alembic upgrade head
uvicorn app.main:app --reload
```

## API

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | – | `{email, password}` → 201 `{id, email}` (bcrypt, min 8 chars) |
| POST | `/auth/login` | – | OAuth2 password form → `{access_token, token_type}` |
| GET | `/auth/me` | JWT | Current user |
| POST | `/api/links` | JWT | Create short link (30/min). `{target_url, custom_code?, title?, expires_at?}` → 201 with `short_url` |
| GET | `/api/links` | JWT | Paginated `?page&per_page&q` → `{items, total}` |
| GET | `/api/links/{id}/stats` | JWT (owner) | `{total_clicks, clicks_by_day[30], top_referrers, top_browsers}` |
| DELETE | `/api/links/{id}` | JWT (owner) | → 204 (also invalidates the Redis cache entry) |
| GET | `/{code}` | – | **307** redirect, records a click. 404 JSON for unknown/expired codes |
| GET | `/health` | – | `{status, db, redis}` |

Interactive docs (themed Cyberpunk/HUD): `/docs`.

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | – | `postgresql+asyncpg://snaplink:snaplink@localhost:5432/snaplink` | SQLAlchemy async URL |
| `JWT_SECRET` | **yes** | – | Secret for signing JWTs (app refuses to boot without it) |
| `JWT_EXPIRE_MINUTES` | – | `60` | Access token lifetime |
| `REDIS_URL` | – | – | e.g. `redis://localhost:6379/0`. Unset = DB-only mode |
| `BASE_URL` | – | `http://localhost:8000` | Public base used to build `short_url` |
| `RATE_LIMIT_ENABLED` | – | `true` | slowapi rate limiting on link creation |

## Privacy & caching notes

- **IP hashing:** visitor IPs are SHA256-hashed before storage (`ip_hash`); raw IPs are never written to the database.
- **Redis is optional:** redirect lookups check Redis first (1h TTL), but every Redis call is wrapped — if Redis is unset or unreachable, the API silently falls back to PostgreSQL. `/health` reports `redis: up|down|disabled`.
- **Tests run on SQLite** (`aiosqlite`) so CI needs no Postgres server; production uses PostgreSQL via the Alembic migration in `alembic/versions/`.

## Files

```
app/            FastAPI app (routers, auth, models, schemas, cache)
alembic/        async env + initial migration (users, links, clicks)
tests/          pytest suite (5 tests, full flow)
docker-compose.yml  api + postgres:16 + redis:7
Dockerfile
```

## Limitations

- Single-instance rate limiting (slowapi in-memory); use a shared backend for multi-replica deploys.
- Click stats aggregate the latest 5,000 clicks per link in Python — fine for demo scale, move to SQL rollups for heavy traffic.
- No live Postgres/Redis in this sandbox: verified against SQLite + cache-disabled mode; the Postgres path is exercised via docker-compose.

## License

**Free to use — just credit devuvo.** Personal, educational, and non-commercial use is free, provided you give visible credit (e.g. "Created by devuvo" with a link to https://www.devuvo.com). Business or income-generating use requires devuvo's prior approval — contact admin@devuvo.com (a license fee may apply). See [LICENSE](LICENSE) for the full terms.
