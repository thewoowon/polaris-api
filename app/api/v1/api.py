from fastapi import APIRouter

from app.api.v1.endpoints import (
    apps,
    audit,
    auth,
    benchmarks,
    classifications,
    companies,
    dashboard,
    ingestion,
    kb,
    policy,
    queue,
    replies,
    reports,
    reviews,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(reviews.router, prefix="/reviews", tags=["reviews"])
api_router.include_router(classifications.router, tags=["classify"])
api_router.include_router(policy.router, prefix="/policy", tags=["policy"])
api_router.include_router(replies.router, prefix="/replies", tags=["replies"])
api_router.include_router(queue.router, prefix="/queue", tags=["queue"])
api_router.include_router(kb.router, prefix="/kb", tags=["kb"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
api_router.include_router(ingestion.router, prefix="/ingestion", tags=["ingestion"])
# Phase 2
api_router.include_router(companies.router, prefix="/companies", tags=["companies"])
api_router.include_router(apps.router, prefix="/apps", tags=["apps"])
api_router.include_router(benchmarks.router, prefix="/benchmarks", tags=["benchmarks"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
