from __future__ import annotations

from fastapi import APIRouter

import api.dependencies as deps
from unisa_air_twin.api_schemas import OperationalHealthResponse
from unisa_air_twin.decision_engine import health_payload

router = APIRouter()


@router.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/ops/health", response_model=OperationalHealthResponse)
def ops_health() -> OperationalHealthResponse:
    settings = deps.get_settings()
    jobs = [job.to_dict() for job in deps.get_job_registry().list(limit=50, settings=settings)]
    return health_payload(deps.get_twin_service().summary(), jobs)
