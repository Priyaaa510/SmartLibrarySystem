"""Reporting & analytics."""

import csv
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from . import clock
from .database import SessionLocal
from .models import (
    Book,
    BookCopy,
    Category,
    Fine,
    FineStatus,
    Loan,
    LoanStatus,
    Reservation,
    ReservationStatus,
    Role,
    User,
)
from .services.catalog import IN_COLLECTION, book_select, to_summary
from .services.circulation import fine_out, loan_out


def _count(db: Session, stmt: Any) -> int:
    return int(db.scalar(stmt) or 0)


def dashboard(db: Session) -> dict[str, Any]:
    today = clock.today()
    copies_by_status: dict[str, int] = dict(
        db.execute(select(BookCopy.status, func.count()).group_by(BookCopy.status)).tuples().all()
    )
    fines = dict(
        db.execute(
            select(Fine.status, func.coalesce(func.sum(Fine.amount), 0)).group_by(Fine.status)
        )
        .tuples()
        .all()
    )
    return {
        "titles": _count(db, select(func.count(Book.id))),
        "copies": sum(v for k, v in copies_by_status.items() if k in IN_COLLECTION),
        "copies_by_status": copies_by_status,
        "categories": _count(db, select(func.count(Category.id))),
        "members": _count(db, select(func.count(User.id)).where(User.role == Role.MEMBER)),
        "active_members": _count(
            db,
            select(func.count(User.id)).where(
                User.role == Role.MEMBER,
                User.is_active.is_(True),
                (User.membership_expiry.is_(None)) | (User.membership_expiry >= today),
            ),
        ),
        "active_loans": _count(
            db, select(func.count(Loan.id)).where(Loan.status == LoanStatus.ACTIVE)
        ),
        "overdue_loans": _count(
            db,
            select(func.count(Loan.id)).where(
                Loan.status == LoanStatus.ACTIVE, Loan.due_date < today
            ),
        ),
        "due_today": _count(
            db,
            select(func.count(Loan.id)).where(
                Loan.status == LoanStatus.ACTIVE, Loan.due_date == today
            ),
        ),
        "issued_today": _count(
            db, select(func.count(Loan.id)).where(cast(Loan.issued_at, Date) == today)
        ),
        "holds_waiting": _count(
            db,
            select(func.count(Reservation.id)).where(
                Reservation.status == ReservationStatus.WAITING
            ),
        ),
        "holds_ready": _count(
            db,
            select(func.count(Reservation.id)).where(Reservation.status == ReservationStatus.READY),
        ),
        "fines_outstanding": float(fines.get(FineStatus.UNPAID, 0)),
        "fines_collected": float(fines.get(FineStatus.PAID, 0)),
        "fines_waived": float(fines.get(FineStatus.WAIVED, 0)),
    }


def circulation_trend(db: Session, days: int = 30) -> list[dict[str, Any]]:
    days = min(max(days, 7), 365)
    start = clock.today() - timedelta(days=days - 1)
    issued: dict[Any, int] = dict(
        db.execute(
            select(cast(Loan.issued_at, Date), func.count())
            .where(cast(Loan.issued_at, Date) >= start)
            .group_by(cast(Loan.issued_at, Date))
        )
        .tuples()
        .all()
    )
    returned: dict[Any, int] = dict(
        db.execute(
            select(cast(Loan.returned_at, Date), func.count())
            .where(Loan.returned_at.is_not(None), cast(Loan.returned_at, Date) >= start)
            .group_by(cast(Loan.returned_at, Date))
        )
        .tuples()
        .all()
    )
    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        out.append(
            {"date": d.isoformat(), "issued": issued.get(d, 0), "returned": returned.get(d, 0)}
        )
    return out


def top_books(db: Session, limit: int = 10) -> list[dict[str, Any]]:
    stmt, cols = book_select()
    rows = db.execute(
        stmt.where(cols["times_borrowed"] > 0)
        .order_by(cols["times_borrowed"].desc(), Book.title)
        .limit(limit)
    ).all()
    return [to_summary(r).model_dump() for r in rows]


def category_breakdown(db: Session) -> list[dict[str, Any]]:
    loans = (
        select(Book.category_id.label("cid"), func.count(Loan.id).label("loans"))
        .join(BookCopy, BookCopy.book_id == Book.id)
        .join(Loan, Loan.copy_id == BookCopy.id)
        .group_by(Book.category_id)
        .subquery()
    )
    titles = (
        select(Book.category_id.label("cid"), func.count(Book.id).label("titles"))
        .group_by(Book.category_id)
        .subquery()
    )
    rows = db.execute(
        select(
            Category.name,
            func.coalesce(titles.c.titles, 0),
            func.coalesce(loans.c.loans, 0),
        )
        .outerjoin(titles, titles.c.cid == Category.id)
        .outerjoin(loans, loans.c.cid == Category.id)
        .order_by(func.coalesce(loans.c.loans, 0).desc(), Category.name)
    ).all()
    return [{"category": n, "titles": t, "loans": loan_count} for n, t, loan_count in rows]


def overdue_report(db: Session) -> list[dict[str, Any]]:
    loans = db.scalars(
        select(Loan)
        .where(Loan.status == LoanStatus.ACTIVE, Loan.due_date < clock.today())
        .order_by(Loan.due_date)
    ).all()
    return [loan_out(loan).model_dump() for loan in loans]


def member_report(member_id: int) -> dict[str, Any]:
    """Runs in a worker thread, so it opens its own session."""
    with SessionLocal() as db:
        member = db.get(User, member_id)
        assert member is not None
        loans = db.scalars(select(Loan).where(Loan.user_id == member_id)).all()
        fines = db.scalars(select(Fine).where(Fine.user_id == member_id)).all()
        return {
            "member_id": member.id,
            "member_code": member.member_code,
            "member": member.name,
            "plan": member.membership_type.name if member.membership_type else None,
            "loans": len(loans),
            "active": sum(loan.status == LoanStatus.ACTIVE for loan in loans),
            "returned": sum(loan.status == LoanStatus.RETURNED for loan in loans),
            "lost": sum(loan.status == LoanStatus.LOST for loan in loans),
            "overdue": sum(
                loan.status == LoanStatus.ACTIVE and loan.due_date < clock.today() for loan in loans
            ),
            "fines_total": float(sum(f.amount for f in fines)),
            "fines_unpaid": float(sum(f.amount for f in fines if f.status == FineStatus.UNPAID)),
        }


def member_reports(db: Session) -> list[dict[str, Any]]:
    ids = list(db.scalars(select(User.id).where(User.role == Role.MEMBER).order_by(User.id)))
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(member_report, ids))


# ---------------------------------------------------------------- CSV export
def _csv(header: list[str], rows: list[list[Any]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    return buf.getvalue()


def export_csv(db: Session, kind: str) -> str | None:
    if kind == "books":
        stmt, _ = book_select()
        rows = [to_summary(r) for r in db.execute(stmt.order_by(Book.title)).all()]
        return _csv(
            ["id", "isbn", "title", "author", "category", "publisher", "year", "language",
             "shelf", "total_copies", "available", "times_borrowed", "avg_rating"],
            [[b.id, b.isbn, b.title, b.author, b.category.name, b.publisher, b.published_year,
              b.language, b.shelf_location, b.total_copies, b.available_copies,
              b.times_borrowed, b.avg_rating] for b in rows],
        )  # fmt: skip
    if kind in ("loans", "overdue"):
        stmt_l = select(Loan).order_by(Loan.issued_at.desc())
        if kind == "overdue":
            stmt_l = stmt_l.where(Loan.status == LoanStatus.ACTIVE, Loan.due_date < clock.today())
        loans = [loan_out(x) for x in db.scalars(stmt_l).all()]
        return _csv(
            ["loan_id", "member_code", "member", "barcode", "title", "issued_at", "due_date",
             "returned_at", "status", "overdue_days", "accrued_fine"],
            [[x.id, x.member_code, x.member_name, x.barcode, x.book_title,
              x.issued_at.isoformat(), x.due_date, x.returned_at, x.status, x.overdue_days,
              x.accrued_fine] for x in loans],
        )  # fmt: skip
    if kind == "fines":
        fines = [fine_out(f) for f in db.scalars(select(Fine).order_by(Fine.created_at.desc()))]
        return _csv(
            ["fine_id", "member", "book", "amount", "reason", "status", "created_at", "note"],
            [[f.id, f.member_name, f.book_title, f.amount, f.reason, f.status,
              f.created_at.isoformat(), f.note] for f in fines],
        )  # fmt: skip
    if kind == "members":
        return _csv(
            ["member_id", "member_code", "member", "plan", "loans", "active", "returned",
             "lost", "overdue", "fines_total", "fines_unpaid"],
            [list(r.values()) for r in member_reports(db)],
        )  # fmt: skip
    return None
