"""Pydantic request/response schemas — the API contract."""
import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

CUSTOM_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{3,16}$")


# --- auth -----------------------------------------------------------------
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --- links ----------------------------------------------------------------
class LinkCreate(BaseModel):
    target_url: str = Field(min_length=1, max_length=2048)
    custom_code: str | None = Field(default=None)
    title: str | None = Field(default=None, max_length=255)
    expires_at: datetime | None = None

    @field_validator("target_url")
    @classmethod
    def _must_be_http_url(cls, v: str) -> str:
        if not re.match(r"^https?://", v.strip(), re.IGNORECASE):
            raise ValueError("target_url must start with http:// or https://")
        return v.strip()

    @field_validator("custom_code")
    @classmethod
    def _valid_custom_code(cls, v: str | None) -> str | None:
        if v is not None and not CUSTOM_CODE_RE.match(v):
            raise ValueError(
                "custom_code must be 3-16 chars of letters, digits, '-' or '_'"
            )
        return v


class LinkOut(BaseModel):
    id: uuid.UUID
    code: str
    target_url: str
    title: str | None
    short_url: str
    click_count: int = 0
    created_at: datetime
    expires_at: datetime | None

    model_config = {"from_attributes": True}


class PaginatedLinks(BaseModel):
    items: list[LinkOut]
    total: int
    page: int
    per_page: int


class ClicksByDay(BaseModel):
    date: str
    count: int


class TopRef(BaseModel):
    referrer: str
    count: int


class TopBrowser(BaseModel):
    browser: str
    count: int


class LinkStats(BaseModel):
    total_clicks: int
    clicks_by_day: list[ClicksByDay]
    top_referrers: list[TopRef]
    top_browsers: list[TopBrowser]


# --- health ---------------------------------------------------------------
class HealthOut(BaseModel):
    status: str
    db: str
    redis: str
