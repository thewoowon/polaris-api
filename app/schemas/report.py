import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.report import ReportStatus, ReportType
from app.schemas.common import ORMModel


class ReportGenerateRequest(BaseModel):
    company_id: uuid.UUID
    app_id: uuid.UUID
    report_type: ReportType = ReportType.COMPANY_APP_REVIEW
    period_start: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    period_end: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    include_benchmark: bool = False
    competitor_app_ids: list[uuid.UUID] = Field(default_factory=list)


class ReportStatusUpdate(BaseModel):
    status: ReportStatus


class ReportResponse(ORMModel):
    id: uuid.UUID
    company_id: uuid.UUID
    app_id: uuid.UUID | None
    report_type: ReportType
    title: str
    period_start: str
    period_end: str
    markdown_content: str
    executive_summary: str
    status: ReportStatus
    created_at: datetime
    updated_at: datetime
    company_name: str | None = None
    app_name: str | None = None
