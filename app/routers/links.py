"""Link CRUD + stats. All routes require auth and are owner-scoped."""
from collections import Counter
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import cache
from ..auth import get_current_user
from ..config import settings
from ..db import get_db
from ..models import Click, Link, User
from ..ratelimit import limiter
from ..schemas import (
    ClicksByDay,
    LinkCreate,
    LinkOut,
    LinkStats,
    PaginatedLinks,
    TopBrowser,
    TopRef,
)
from ..services.geo import parse_user_agent
from ..services.shortcode import generate_code

router = APIRouter(prefix="/api/links", tags=["links"])


def _to_out(link: Link, click_count: int = 0) -> LinkOut:
    return LinkOut(
        id=link.id,
        code=link.code,
        target_url=link.target_url,
        title=link.title,
        short_url=f"{settings.BASE_URL.rstrip('/')}/{link.code}",
        click_count=click_count,
        created_at=link.created_at,
        expires_at=link.expires_at,
    )


async def _unique_code(db: AsyncSession, wanted: str | None) -> str:
    """Custom code if free, else random base62 with collision retry."""
    if wanted:
        exists = await db.scalar(select(Link.id).where(Link.code == wanted))
        if exists:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Custom code already taken",
            )
        return wanted
    for _ in range(10):
        code = generate_code()
        exists = await db.scalar(select(Link.id).where(Link.code == code))
        if not exists:
            return code
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Could not generate a unique code, try again",
    )


async def _get_owned_link(
    link_id: str, user: User, db: AsyncSession
) -> Link:
    try:
        from uuid import UUID

        uid = UUID(link_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Link not found")
    link = await db.scalar(
        select(Link).where(Link.id == uid, Link.user_id == user.id)
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Link not found")
    return link


@router.post("", response_model=LinkOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def create_link(
    request: Request,
    body: LinkCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    code = await _unique_code(db, body.custom_code)
    link = Link(
        user_id=user.id,
        code=code,
        target_url=body.target_url,
        title=body.title,
        expires_at=body.expires_at,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return _to_out(link)


@router.get("", response_model=PaginatedLinks)
async def list_links(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, max_length=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Link).where(Link.user_id == user.id)
    count_stmt = select(func.count()).select_from(Link).where(Link.user_id == user.id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            Link.code.ilike(like)
            | Link.target_url.ilike(like)
            | Link.title.ilike(like)
        )
        count_stmt = count_stmt.where(
            Link.code.ilike(like)
            | Link.target_url.ilike(like)
            | Link.title.ilike(like)
        )
    total = await db.scalar(count_stmt) or 0
    links = (
        (
            await db.scalars(
                stmt.order_by(Link.created_at.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
                .options(selectinload(Link.clicks))
            )
        )
        .unique()
        .all()
    )
    items = [_to_out(link, len(link.clicks)) for link in links]
    return PaginatedLinks(items=items, total=total, page=page, per_page=per_page)


@router.get("/{link_id}/stats", response_model=LinkStats)
async def link_stats(
    link_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    link = await _get_owned_link(link_id, user, db)
    clicks = (
        await db.scalars(
            select(Click)
            .where(Click.link_id == link.id)
            .order_by(Click.clicked_at.desc())
            .limit(5000)
        )
    ).all()

    by_day: Counter[str] = Counter()
    referrers: Counter[str] = Counter()
    browsers: Counter[str] = Counter()
    for c in clicks:
        day = c.clicked_at.date().isoformat() if c.clicked_at else "unknown"
        by_day[day] += 1
        referrers[c.referrer or "(direct)"] += 1
        browsers[parse_user_agent(c.user_agent)["browser"]] += 1

    # last 30 days, oldest → newest, zero-filled
    today = datetime.utcnow().date()
    days = [
        ClicksByDay(
            date=(today - timedelta(days=i)).isoformat(),
            count=by_day.get((today - timedelta(days=i)).isoformat(), 0),
        )
        for i in range(29, -1, -1)
    ]
    return LinkStats(
        total_clicks=len(clicks),
        clicks_by_day=days,
        top_referrers=[
            TopRef(referrer=r, count=n) for r, n in referrers.most_common(10)
        ],
        top_browsers=[
            TopBrowser(browser=b, count=n) for b, n in browsers.most_common(10)
        ],
    )


@router.delete("/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(
    link_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    link = await _get_owned_link(link_id, user, db)
    await db.delete(link)
    await db.commit()
    await cache.invalidate_target(link.code)
    return None
