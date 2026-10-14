from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy import func, select, update

from ..errors import NotFound
from ..models import (
    Fine,
    FineStatus,
    Loan,
    LoanStatus,
    Notification,
    Reservation,
    ReservationStatus,
    User,
)
from ..recommendations import STRATEGIES
from ..schemas import BookSummary, Message, MySummary, NotificationOut, UserOut
from ..security import DB, CurrentUser
from ..services import circulation as svc
from ..services.common import get_or_404

router = APIRouter(prefix="/api", tags=["my account"])


@router.get("/me/summary", response_model=MySummary)
def my_summary(db: DB, user: CurrentUser) -> MySummary:
    loans = db.scalars(
        select(Loan)
        .where(Loan.user_id == user.id, Loan.status == LoanStatus.ACTIVE)
        .order_by(Loan.due_date)
    ).all()
    holds = db.scalars(
        select(Reservation)
        .where(
            Reservation.user_id == user.id,
            Reservation.status.in_([ReservationStatus.WAITING, ReservationStatus.READY]),
        )
        .order_by(Reservation.created_at)
    ).all()
    fines = db.scalars(
        select(Fine)
        .where(Fine.user_id == user.id, Fine.status == FineStatus.UNPAID)
        .order_by(Fine.created_at.desc())
    ).all()
    return MySummary(
        user=UserOut.model_validate(user),
        eligibility=svc.eligibility(db, user),
        active_loans=[svc.loan_out(x) for x in loans],
        reservations=[svc.reservation_out(db, r) for r in holds],
        unpaid_fines=[svc.fine_out(f) for f in fines],
        total_borrowed=db.scalar(select(func.count(Loan.id)).where(Loan.user_id == user.id)) or 0,
        unread_notifications=db.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == user.id, Notification.is_read.is_(False)
            )
        )
        or 0,
    )


# ---------------------------------------------------------------- notifications
@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(
    db: DB, user: CurrentUser, unread_only: bool = False, limit: int = 50
) -> list[Notification]:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    return list(db.scalars(stmt.order_by(Notification.created_at.desc()).limit(min(limit, 200))))


@router.get("/notifications/unread-count")
def unread_count(db: DB, user: CurrentUser) -> dict[str, int]:
    n = db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == user.id, Notification.is_read.is_(False)
        )
    )
    return {"unread": n or 0}


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: int, db: DB, user: CurrentUser) -> Notification:
    note = db.get(Notification, notification_id)
    if note is None or note.user_id != user.id:
        raise NotFound("Notification not found")
    note.is_read = True
    db.commit()
    return note


@router.post("/notifications/read-all", response_model=Message)
def mark_all_read(db: DB, user: CurrentUser) -> Message:
    db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    db.commit()
    return Message(detail="All notifications marked as read")


# ---------------------------------------------------------------- recommendations
@router.get("/recommendations/strategies")
def strategies() -> list[dict[str, Any]]:
    return [{"name": s.name, "description": s.description} for s in STRATEGIES.values()]


@router.get("/recommendations", response_model=list[BookSummary])
def recommendations(
    db: DB,
    user: CurrentUser,
    strategy: Annotated[str, Query(pattern="^(hybrid|category|history|popular)$")] = "hybrid",
    member_id: int | None = None,
    limit: int = 8,
) -> list[BookSummary]:
    member = user
    if member_id is not None and user.is_staff:
        member = get_or_404(db, User, member_id, "Member")
    return STRATEGIES[strategy].recommend(db, member, min(max(limit, 1), 24))
