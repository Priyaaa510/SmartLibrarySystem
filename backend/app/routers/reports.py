from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response
from sqlalchemy import func, select

from .. import clock, reports
from ..errors import NotFound
from ..models import AuditLog
from ..performance import compare
from ..schemas import AuditOut, JobResult, LoanOut, Page
from ..security import DB, Staff
from ..services.circulation import run_daily_jobs
from ..services.common import paginate_args

router = APIRouter(prefix="/api", tags=["reports & admin"])


@router.get("/reports/dashboard")
def dashboard(db: DB, staff: Staff) -> dict[str, Any]:
    return reports.dashboard(db)


@router.get("/reports/circulation")
def circulation(db: DB, staff: Staff, days: int = 30) -> list[dict[str, Any]]:
    return reports.circulation_trend(db, days)


@router.get("/reports/top-books")
def top_books(db: DB, staff: Staff, limit: int = 10) -> list[dict[str, Any]]:
    return reports.top_books(db, min(max(limit, 1), 50))


@router.get("/reports/categories")
def categories(db: DB, staff: Staff) -> list[dict[str, Any]]:
    return reports.category_breakdown(db)


@router.get("/reports/overdue", response_model=list[LoanOut])
def overdue(db: DB, staff: Staff) -> list[dict[str, Any]]:
    return reports.overdue_report(db)


@router.get("/reports/members")
def member_reports(db: DB, staff: Staff) -> list[dict[str, Any]]:
    """Per-member statistics, computed concurrently with a thread pool."""
    return reports.member_reports(db)


@router.get("/reports/export/{kind}.csv")
def export(kind: str, db: DB, staff: Staff) -> Response:
    data = reports.export_csv(db, kind)
    if data is None:
        raise NotFound("Unknown export - use books, loans, overdue, fines or members")
    filename = f"{kind}-{clock.today().isoformat()}.csv"
    return Response(
        content=data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/activity", response_model=Page[AuditOut])
def activity(
    db: DB, staff: Staff, action: str | None = None, page: int = 1, size: int = 30
) -> Page[AuditOut]:
    page, size = paginate_args(page, size)
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action.startswith(action))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    items = [
        AuditOut(
            id=r.id,
            actor=r.actor.name if r.actor else "System",
            action=r.action,
            entity=r.entity,
            entity_id=r.entity_id,
            details=r.details,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return Page(items=items, total=total, page=page, size=size)


@router.post("/admin/run-daily-jobs", response_model=JobResult)
def daily_jobs(db: DB, staff: Staff) -> JobResult:
    result = run_daily_jobs(db)
    db.commit()
    return JobResult(**result)


@router.get("/performance")
def performance(db: DB) -> dict[str, Any]:
    return compare(db)
