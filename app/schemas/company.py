import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.company import Industry
from app.schemas.common import ORMModel


class CompanyCreate(BaseModel):
    name: str = Field(..., max_length=256)
    industry: Industry
    homepage_url: str | None = Field(None, max_length=512)
    contact_email: str | None = Field(None, max_length=256)
    memo: str | None = None


class CompanyUpdate(BaseModel):
    name: str | None = Field(None, max_length=256)
    industry: Industry | None = None
    homepage_url: str | None = None
    contact_email: str | None = None
    memo: str | None = None


class CompanyResponse(ORMModel):
    id: uuid.UUID
    name: str
    industry: Industry
    homepage_url: str | None
    contact_email: str | None
    memo: str | None
    created_at: datetime
    updated_at: datetime
    app_count: int = 0
