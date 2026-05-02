from datetime import date

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    total_reviews: int
    negative_ratio: float
    auto_reply_rate: float
    human_review_rate: float
    high_risk_count: int


class TrendPoint(BaseModel):
    day: date
    total: int
    negative: int


class CategoryBreakdown(BaseModel):
    category: str
    count: int
    share: float


class HighRiskItem(BaseModel):
    review_id: int
    action: str
    risk_score: float
    category: str
    created_at: str
