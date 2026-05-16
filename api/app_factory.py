from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import api.dependencies as deps
from api.autostart import auto_ingest_loop
from api.realtime import realtime_notification_loop
from api.routers import frontend, health, jobs, twin


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = deps.get_settings()
    ingest_task = asyncio.create_task(auto_ingest_loop(settings, deps.get_twin_service, deps.get_snapshot_events()))
    realtime_task = asyncio.create_task(realtime_notification_loop(settings, deps.get_snapshot_events()))
    try:
        yield
    finally:
        ingest_task.cancel()
        realtime_task.cancel()
        with suppress(asyncio.CancelledError):
            await ingest_task
        with suppress(asyncio.CancelledError):
            await realtime_task


def create_app() -> FastAPI:
    app = FastAPI(
        title="UNISA Air Quality Digital Twin API",
        version="0.1.0",
        description="Operational API for real-only UNISA sensor snapshots, raw histories, and campus context layers.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(jobs.router)
    app.include_router(twin.router)
    app.include_router(frontend.router)
    return app
