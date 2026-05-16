import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.app_profile import Platform
from app.schemas.common import ORMModel


class AppProfileCreate(BaseModel):
    company_id: uuid.UUID
    app_name: str = Field(..., max_length=256)
    platform: Platform
    app_store_id: str | None = Field(None, max_length=128)
    play_store_package: str | None = Field(None, max_length=256)
    category: str | None = Field(None, max_length=64)
    country: str = Field("kr", max_length=8)
    is_target: bool = False
    is_competitor: bool = False


class AppProfileUpdate(BaseModel):
    app_name: str | None = Field(None, max_length=256)
    platform: Platform | None = None
    app_store_id: str | None = None
    play_store_package: str | None = None
    category: str | None = None
    is_target: bool | None = None
    is_competitor: bool | None = None


class AppProfileResponse(ORMModel):
    id: uuid.UUID
    company_id: uuid.UUID
    app_name: str
    platform: Platform
    app_store_id: str | None
    play_store_package: str | None
    category: str | None
    country: str
    is_target: bool
    is_competitor: bool
    created_at: datetime
    updated_at: datetime
    review_count: int = 0
    average_rating: float | None = None
    negative_ratio: float | None = None
    company_name: str | None = None
