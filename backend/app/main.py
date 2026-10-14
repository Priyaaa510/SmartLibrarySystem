import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from .config import settings
from .database import Base, SessionLocal, engine
from .errors import LibraryError
from .routers import account, auth, catalog, circulation, members, reports
from .seed import seed
from .services.circulation import run_daily_jobs

log = logging.getLogger("smart_library")


def _run_jobs_once() -> dict[str, int]:
    with SessionLocal() as db:
        result = run_daily_jobs(db)
        db.commit()
        return result


async def _scheduler() -> None:
    """Background loop: expire uncollected holds and send due/overdue reminders."""
    while True:
        try:
            result = await asyncio.to_thread(_run_jobs_once)
            log.info("Daily jobs: %s", result)
        except Exception:  # pragma: no cover - keep the loop alive
            log.exception("Scheduled job failed")
        await asyncio.sleep(settings.scheduler_interval_minutes * 60)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(engine)
    if settings.seed_demo_data:
        with SessionLocal() as db:
            if seed(db):
                log.info("Seeded demo data")
    task = asyncio.create_task(_scheduler()) if settings.run_scheduler else None
    yield
    if task:
        task.cancel()


app = FastAPI(
    title="Smart Library Management API",
    version="2.0.0",
    description="Library management with PostgreSQL: catalog, circulation, holds, fines, "
    "members, recommendations and reports. Use **Authorize** with a token from /api/auth/login.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(LibraryError)
async def library_error(_: Request, exc: LibraryError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(IntegrityError)
async def integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
    log.warning("Integrity error: %s", exc.orig)
    return JSONResponse(
        status_code=409, content={"detail": "This conflicts with existing data - please refresh"}
    )


@app.get("/api/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


for module in (auth, catalog, members, circulation, account, reports):
    app.include_router(module.router)
