from typing import Any

from fastapi import APIRouter
from sqlalchemy import func, or_, select

from .. import clock
from ..models import (
    Book,
    BookCopy,
    Fine,
    FineStatus,
    Loan,
    LoanStatus,
    Reservation,
    ReservationStatus,
    User,
)
from ..schemas import (
    CheckinIn,
    CheckoutIn,
    FineIn,
    FineOut,
    FineSettle,
    LoanOut,
    Page,
    ReservationIn,
    ReservationOut,
    ReturnIn,
    ReturnOut,
)
from ..security import DB, CurrentUser, Staff
from ..services import circulation as svc
from ..services.common import audit, get_or_404, notify, paginate_args

router = APIRouter(prefix="/api", tags=["circulation"])


def _return_out(db: DB, result: svc.ReturnResult) -> ReturnOut:
    for fine in result.fines:
        db.refresh(fine)
    return ReturnOut(
        loan=svc.loan_out(result.loan),
        fines=[svc.fine_out(f) for f in result.fines],
        hold_assigned_to=result.hold.user.name if result.hold else None,
    )


# ---------------------------------------------------------------- loans
@router.get("/loans", response_model=Page[LoanOut])
def list_loans(
    db: DB,
    user: CurrentUser,
    status: str | None = None,
    member_id: int | None = None,
    q: str = "",
    page: int = 1,
    size: int = 20,
) -> Page[LoanOut]:
    """Staff see all loans; members only see their own."""
    page, size = paginate_args(page, size)
    stmt = (
        select(Loan)
        .join(BookCopy, Loan.copy_id == BookCopy.id)
        .join(Book)
        .join(User, Loan.user_id == User.id)
    )
    if not user.is_staff:
        member_id = user.id
    if member_id:
        stmt = stmt.where(Loan.user_id == member_id)
    if status == "overdue":
        stmt = stmt.where(Loan.status == LoanStatus.ACTIVE, Loan.due_date < clock.today())
    elif status == "due_today":
        stmt = stmt.where(Loan.status == LoanStatus.ACTIVE, Loan.due_date == clock.today())
    elif status:
        stmt = stmt.where(Loan.status == status)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Book.title.ilike(like),
                BookCopy.barcode.ilike(like),
                User.name.ilike(like),
                User.member_code.ilike(like),
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order: list[Any] = (
        [Loan.due_date.asc()]
        if status in ("active", "overdue")
        else [(Loan.status == LoanStatus.ACTIVE).desc(), Loan.issued_at.desc()]
    )
    loans = db.scalars(stmt.order_by(*order).offset((page - 1) * size).limit(size)).all()
    return Page(items=[svc.loan_out(x) for x in loans], total=total, page=page, size=size)


@router.post("/loans/checkout", response_model=LoanOut, status_code=201)
def checkout(data: CheckoutIn, db: DB, staff: Staff) -> LoanOut:
    loan = svc.checkout(
        db, staff, data.member, barcode=data.barcode, book_id=data.book_id, due_date=data.due_date
    )
    db.commit()
    return svc.loan_out(loan)


@router.post("/loans/checkin", response_model=ReturnOut)
def checkin(data: CheckinIn, db: DB, staff: Staff) -> ReturnOut:
    result = svc.checkin_by_barcode(db, staff, data.barcode, **data.model_dump(exclude={"barcode"}))
    db.commit()
    return _return_out(db, result)


@router.post("/loans/{loan_id}/return", response_model=ReturnOut)
def return_loan(loan_id: int, db: DB, staff: Staff, data: ReturnIn | None = None) -> ReturnOut:
    result = svc.return_loan(db, staff, loan_id, **(data or ReturnIn()).model_dump())
    db.commit()
    return _return_out(db, result)


@router.post("/loans/{loan_id}/renew", response_model=LoanOut)
def renew(loan_id: int, db: DB, user: CurrentUser) -> LoanOut:
    loan = svc.renew(db, user, loan_id)
    db.commit()
    return svc.loan_out(loan)


@router.post("/loans/{loan_id}/lost", response_model=ReturnOut)
def mark_lost(loan_id: int, db: DB, staff: Staff) -> ReturnOut:
    result = svc.mark_lost(db, staff, loan_id)
    db.commit()
    return _return_out(db, result)


# ---------------------------------------------------------------- reservations
@router.get("/reservations", response_model=Page[ReservationOut])
def list_reservations(
    db: DB,
    user: CurrentUser,
    status: str | None = None,
    member_id: int | None = None,
    book_id: int | None = None,
    page: int = 1,
    size: int = 20,
) -> Page[ReservationOut]:
    page, size = paginate_args(page, size)
    stmt = select(Reservation)
    if not user.is_staff:
        member_id = user.id
    if member_id:
        stmt = stmt.where(Reservation.user_id == member_id)
    if book_id:
        stmt = stmt.where(Reservation.book_id == book_id)
    if status == "open":
        stmt = stmt.where(
            Reservation.status.in_([ReservationStatus.WAITING, ReservationStatus.READY])
        )
    elif status:
        stmt = stmt.where(Reservation.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(
            (Reservation.status == ReservationStatus.READY).desc(),
            (Reservation.status == ReservationStatus.WAITING).desc(),
            Reservation.created_at,
        )
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return Page(items=[svc.reservation_out(db, r) for r in rows], total=total, page=page, size=size)


@router.post("/reservations", response_model=ReservationOut, status_code=201)
def place_hold(data: ReservationIn, db: DB, user: CurrentUser) -> ReservationOut:
    res = svc.place_hold(db, user, data.book_id, data.member_id)
    db.commit()
    return svc.reservation_out(db, res)


@router.post("/reservations/{reservation_id}/cancel", response_model=ReservationOut)
def cancel_hold(reservation_id: int, db: DB, user: CurrentUser) -> ReservationOut:
    res = svc.cancel_hold(db, user, reservation_id)
    db.commit()
    return svc.reservation_out(db, res)


# ---------------------------------------------------------------- fines
@router.get("/fines", response_model=Page[FineOut])
def list_fines(
    db: DB,
    user: CurrentUser,
    status: str | None = None,
    member_id: int | None = None,
    page: int = 1,
    size: int = 20,
) -> Page[FineOut]:
    page, size = paginate_args(page, size)
    stmt = select(Fine)
    if not user.is_staff:
        member_id = user.id
    if member_id:
        stmt = stmt.where(Fine.user_id == member_id)
    if status:
        stmt = stmt.where(Fine.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by((Fine.status == FineStatus.UNPAID).desc(), Fine.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return Page(items=[svc.fine_out(f) for f in rows], total=total, page=page, size=size)


@router.post("/fines", response_model=FineOut, status_code=201)
def add_fine(data: FineIn, db: DB, staff: Staff) -> FineOut:
    member = get_or_404(db, User, data.member_id, "Member")
    fine = Fine(
        user_id=member.id,
        amount=svc.money(data.amount),
        reason=data.reason,
        note=data.note,
        status=FineStatus.UNPAID,
    )
    db.add(fine)
    db.flush()
    notify(
        db,
        member.id,
        "fine",
        "New charge on your account",
        f"A {data.reason} charge of ₹{fine.amount} was added. {data.note or ''}".strip(),
    )
    audit(db, staff, "fine.create", "fine", fine.id, f"₹{fine.amount} {member.name}")
    db.commit()
    db.refresh(fine)
    return svc.fine_out(fine)


@router.post("/fines/{fine_id}/pay", response_model=FineOut)
def pay_fine(fine_id: int, db: DB, user: CurrentUser, data: FineSettle | None = None) -> FineOut:
    fine = svc.settle_fine(db, user, fine_id, waive=False, note=data.note if data else None)
    db.commit()
    return svc.fine_out(fine)


@router.post("/fines/{fine_id}/waive", response_model=FineOut)
def waive_fine(fine_id: int, db: DB, staff: Staff, data: FineSettle | None = None) -> FineOut:
    fine = svc.settle_fine(db, staff, fine_id, waive=True, note=data.note if data else None)
    db.commit()
    return svc.fine_out(fine)
