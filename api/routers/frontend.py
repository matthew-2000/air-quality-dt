from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

import api.dependencies as deps

router = APIRouter()


@router.get("/", include_in_schema=False)
def frontend_index() -> Response:
    index_path = deps.frontend_index_path()
    if not index_path.exists():
        raise HTTPException(status_code=503, detail="Frontend assets not available")
    return FileResponse(index_path)


@router.get("/{full_path:path}", include_in_schema=False)
def frontend_routes(full_path: str) -> Response:
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    index_path = deps.frontend_index_path()
    if not index_path.exists():
        raise HTTPException(status_code=503, detail="Frontend assets not available")
    asset = deps.frontend_file(full_path)
    if asset is not None:
        return FileResponse(asset)
    return FileResponse(index_path)
