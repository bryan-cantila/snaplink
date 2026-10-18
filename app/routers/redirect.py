"""Public redirect: GET /{code} → 307 to the target URL.

Lookup order: Redis cache (if configured and reachable) → database.
Every hit records a click (referrer, user-agent, SHA256 of the IP —
raw IPs are never stored). Unknown or expired codes → 404 JSON.

Registered LAST in main.py so it never shadows /docs, /api/*, /auth/*.
"""
import hashlib
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import cache
from ..db import get_db
from ..models import Click, Link

router = APIRouter(tags=["redirect"])


def _ip_hash(request: Request) -> str | None:
    if request.client and request.client.host:
        return hashlib.sha256(request.client.host.encode()).hexdigest()
    return None


def _is_expired(expires_at: datetime | None) -> bool:
    """Timezone-safe expiry check (SQLite returns naive, Postgres aware)."""
    if expires_at is None:
        return False
    if expires_at.tzinfo is not None:
        expires_at = expires_at.replace(tzinfo=None)
    return expires_at < datetime.utcnow()


@router.get("/{code}")
async def redirect_code(code: str, request: Request, db: AsyncSession = Depends(get_db)):
    link_id: str | None = None
    target: str | None = None

    cached = await cache.get_target(code)
    if cached:
        try:
            payload = json.loads(cached)
            link_id, target = payload["id"], payload["url"]
        except (json.JSONDecodeError, KeyError):
            target = None

    link: Link | None = None
    if target is None:
        link = await db.scalar(select(Link).where(Link.code == code))
        if link is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Unknown short code"
            )
        if _is_expired(link.expires_at):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Link has expired"
            )
        link_id, target = str(link.id), link.target_url
        await cache.set_target(code, json.dumps({"id": link_id, "url": target}))

    # record the click (best-effort: a tracking failure must not break redirects)
    try:
        db.add(
            Click(
                link_id=uuid.UUID(link_id),
                referrer=request.headers.get("referer"),
                user_agent=request.headers.get("user-agent"),
                ip_hash=_ip_hash(request),
            )
        )
        await db.commit()
    except Exception:
        await db.rollback()

    return RedirectResponse(url=target, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
