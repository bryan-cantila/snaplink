"""Full API flow tests.

They run against SQLite (aiosqlite) so CI needs no Postgres server.
Production runs on PostgreSQL via the Alembic migration + docker-compose;
the app code itself is backend-agnostic.
"""
import os

os.environ["JWT_SECRET"] = "test-secret-not-for-production"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["RATE_LIMIT_ENABLED"] = "false"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app

TEST_ENGINE = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = async_sessionmaker(
    TEST_ENGINE, expire_on_commit=False, class_=AsyncSession
)


async def override_get_db():
    async with TestSession() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def _fresh_db():
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest_asyncio.fixture()
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def _register(client, email="ada@example.com", password="supersecret1"):
    return await client.post(
        "/auth/register", json={"email": email, "password": password}
    )


async def _login(client, email="ada@example.com", password="supersecret1"):
    r = await client.post(
        "/auth/login", data={"username": email, "password": password}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_register_login_flow(client):
    r = await _register(client)
    assert r.status_code == 201, r.text
    assert r.json()["email"] == "ada@example.com"

    dup = await _register(client)
    assert dup.status_code == 400

    short_pw = await _register(client, email="b@example.com", password="short")
    assert short_pw.status_code == 422

    bad_login = await client.post(
        "/auth/login", data={"username": "ada@example.com", "password": "wrongpass1"}
    )
    assert bad_login.status_code == 401

    headers = await _login(client)
    me = await client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "ada@example.com"


async def test_create_and_redirect_and_stats(client):
    await _register(client)
    headers = await _login(client)

    # unauthenticated create → 401
    r = await client.post("/api/links", json={"target_url": "https://example.com"})
    assert r.status_code == 401

    # create with custom code
    r = await client.post(
        "/api/links",
        json={"target_url": "https://example.com/page", "custom_code": "demo123",
              "title": "Demo"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["code"] == "demo123"
    assert body["short_url"].endswith("/demo123")
    link_id = body["id"]

    # duplicate custom code → 409
    r = await client.post(
        "/api/links",
        json={"target_url": "https://example.com/other", "custom_code": "demo123"},
        headers=headers,
    )
    assert r.status_code == 409

    # invalid custom code → 422
    r = await client.post(
        "/api/links",
        json={"target_url": "https://example.com/", "custom_code": "no spaces!"},
        headers=headers,
    )
    assert r.status_code == 422

    # non-http url → 422
    r = await client.post(
        "/api/links", json={"target_url": "ftp://example.com"}, headers=headers
    )
    assert r.status_code == 422

    # random code create
    r = await client.post(
        "/api/links", json={"target_url": "https://example.org"}, headers=headers
    )
    assert r.status_code == 201
    assert len(r.json()["code"]) == 7

    # list + search
    r = await client.get("/api/links", headers=headers)
    assert r.status_code == 200
    assert r.json()["total"] == 2
    r = await client.get("/api/links?q=demo123", headers=headers)
    assert r.json()["total"] == 1

    # redirect (public, no auth) → 307 + click tracked
    r = await client.get("/demo123", follow_redirects=False)
    assert r.status_code == 307, r.text
    assert r.headers["location"] == "https://example.com/page"

    # unknown code → 404 JSON
    r = await client.get("/nope-not-real", follow_redirects=False)
    assert r.status_code == 404
    assert r.json()["detail"] == "Unknown short code"

    # stats
    r = await client.get(f"/api/links/{link_id}/stats", headers=headers)
    assert r.status_code == 200, r.text
    stats = r.json()
    assert stats["total_clicks"] == 1
    assert sum(d["count"] for d in stats["clicks_by_day"]) == 1
    assert len(stats["clicks_by_day"]) == 30

    # delete → 204, then redirect 404s
    r = await client.delete(f"/api/links/{link_id}", headers=headers)
    assert r.status_code == 204
    r = await client.get("/demo123", follow_redirects=False)
    assert r.status_code == 404


async def test_owner_isolation(client):
    await _register(client, email="one@example.com")
    h1 = await _login(client, email="one@example.com")
    await _register(client, email="two@example.com")
    h2 = await _login(client, email="two@example.com")

    r = await client.post(
        "/api/links",
        json={"target_url": "https://example.com", "custom_code": "private1"},
        headers=h1,
    )
    link_id = r.json()["id"]

    # user two cannot see / stats / delete user one's link
    assert (await client.get("/api/links", headers=h2)).json()["total"] == 0
    assert (
        await client.get(f"/api/links/{link_id}/stats", headers=h2)
    ).status_code == 404
    assert (
        await client.delete(f"/api/links/{link_id}", headers=h2)
    ).status_code == 404


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert body["db"] == "up"  # sqlite in tests
    assert body["redis"] == "disabled"  # no REDIS_URL in tests


async def test_expired_link_redirects_404(client):
    await _register(client)
    headers = await _login(client)
    r = await client.post(
        "/api/links",
        json={
            "target_url": "https://example.com",
            "custom_code": "oldlink1",
            "expires_at": "2000-01-01T00:00:00",
        },
        headers=headers,
    )
    assert r.status_code == 201
    r = await client.get("/oldlink1", follow_redirects=False)
    assert r.status_code == 404
    assert r.json()["detail"] == "Link has expired"
