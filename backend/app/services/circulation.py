"""Circulation rules: issue, return, renew, lost items, holds queue and fines."""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import clock
from ..config import settings
from ..errors import Conflict, Forbidden, LibraryError, NotFound
from ..models import (
    Book,
    BookCopy,
    CopyStatus,
    Fine,
    FineReason,
    FineStatus,
    Loan,
    LoanStatus,
    Reservation,
    ReservationStatus,
    User,
)
from ..schemas import Eligibility, FineOut, LoanOut, ReservationOut
from .common import audit, get_or_404, notify


# ---------------------------------------------------------------- helpers
def fine_rate(user: User) -> Decimal:
    mt = user.membership_type
    return mt.fine_per_day if mt else settings.default_fine_per_day


def overdue_days(loan: Loan, on: date | None = None) -> int:
    if loan.status == LoanStatus.RETURNED and loan.returned_at is not None:
        end = loan.returned_at.date()
    else:
        end = on or clock.today()
    return max(0, (end - loan.due_date).days)


def accrued_fine(loan: Loan) -> Decimal:
    if loan.status != LoanStatus.ACTIVE:
        return Decimal("0")
    return overdue_days(loan) * fine_rate(loan.user)


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def loan_out(loan: Loan) -> LoanOut:
    book = loan.copy.book
    days = overdue_days(loan)
    mt = loan.user.membership_type
    return LoanOut(
        id=loan.id,
        status=loan.status,
        issued_at=loan.issued_at,
        due_date=loan.due_date,
        returned_at=loan.returned_at,
        renew_count=loan.renew_count,
        max_renewals=mt.max_renewals if mt else 0,
        is_overdue=loan.status == LoanStatus.ACTIVE and days > 0,
        overdue_days=days,
        accrued_fine=float(accrued_fine(loan)),
        member_id=loan.user_id,
        member_name=loan.user.name,
        member_code=loan.user.member_code,
        copy_id=loan.copy_id,
        barcode=loan.copy.barcode,
        book_id=book.id,
        book_title=book.title,
        book_author=book.author,
        cover_url=book.cover_url,
    )


def queue_position(db: Session, res: Reservation) -> int | None:
    if res.status != ReservationStatus.WAITING:
        return None
    ahead = db.scalar(
        select(func.count()).where(
            Reservation.book_id == res.book_id,
            Reservation.status == ReservationStatus.WAITING,
            Reservation.created_at < res.created_at,
        )
    )
    return (ahead or 0) + 1


def reservation_out(db: Session, res: Reservation) -> ReservationOut:
    return ReservationOut(
        id=res.id,
        status=res.status,
        created_at=res.created_at,
        ready_at=res.ready_at,
        expires_on=res.expires_on,
        closed_at=res.closed_at,
        queue_position=queue_position(db, res),
        member_id=res.user_id,
        member_name=res.user.name,
        book_id=res.book_id,
        book_title=res.book.title,
        book_author=res.book.author,
        barcode=res.copy.barcode if res.copy else None,
    )


def fine_out(fine: Fine) -> FineOut:
    return FineOut(
        id=fine.id,
        member_id=fine.user_id,
        member_name=fine.user.name,
        loan_id=fine.loan_id,
        book_title=fine.loan.copy.book.title if fine.loan else None,
        amount=float(fine.amount),
        reason=fine.reason,
        status=fine.status,
        note=fine.note,
        created_at=fine.created_at,
        settled_at=fine.settled_at,
    )


def active_loan_count(db: Session, user_id: int) -> int:
    return (
        db.scalar(
            select(func.count()).where(Loan.user_id == user_id, Loan.status == LoanStatus.ACTIVE)
        )
        or 0
    )


def unpaid_fines_total(db: Session, user_id: int) -> Decimal:
    total = db.scalar(
        select(func.coalesce(func.sum(Fine.amount), 0)).where(
            Fine.user_id == user_id, Fine.status == FineStatus.UNPAID
        )
    )
    return Decimal(total or 0)


def overdue_loan_count(db: Session, user_id: int) -> int:
    return (
        db.scalar(
            select(func.count()).where(
                Loan.user_id == user_id,
                Loan.status == LoanStatus.ACTIVE,
                Loan.due_date < clock.today(),
            )
        )
        or 0
    )


def eligibility(db: Session, member: User) -> Eligibility:
    reasons: list[str] = []
    mt = member.membership_type
    active = active_loan_count(db, member.id)
    unpaid = unpaid_fines_total(db, member.id)
    if not member.is_active:
        reasons.append("Account is deactivated")
    if mt is None:
        reasons.append("No membership plan assigned")
    if member.membership_expiry and member.membership_expiry < clock.today():
        reasons.append(f"Membership expired on {member.membership_expiry.isoformat()}")
    if mt and active >= mt.max_books:
        reasons.append(f"Borrowing limit reached ({active}/{mt.max_books})")
    if mt and unpaid > mt.max_unpaid_fine:
        reasons.append(f"Unpaid fines ₹{unpaid} exceed the limit of ₹{mt.max_unpaid_fine}")
    overdue = overdue_loan_count(db, member.id)
    if overdue:
        reasons.append(f"{overdue} overdue item(s) must be returned first")
    return Eligibility(
        can_borrow=not reasons,
        reasons=reasons,
        active_loans=active,
        max_books=mt.max_books if mt else 0,
        unpaid_fines=float(unpaid),
    )


def resolve_member(db: Session, ref: str | int) -> User:
    ref = str(ref).strip()
    member: User | None
    if ref.isdigit():
        member = db.get(User, int(ref))
    else:
        member = db.scalar(select(User).where(func.upper(User.member_code) == ref.upper()))
    if member is None:
        raise NotFound(f"Member '{ref}' not found")
    return member


def _open_reservation(db: Session, book_id: int, user_id: int) -> Reservation | None:
    return db.scalar(
        select(Reservation).where(
            Reservation.book_id == book_id,
            Reservation.user_id == user_id,
            Reservation.status.in_([ReservationStatus.WAITING, ReservationStatus.READY]),
        )
    )


def _close_reservation(res: Reservation, status: ReservationStatus) -> None:
    res.status = status
    res.closed_at = clock.now()


# ---------------------------------------------------------------- holds shelf
def release_copy(db: Session, copy: BookCopy, actor: User | None) -> Reservation | None:
    """A copy came back to the shelf: give it to the next member in the queue, if any."""
    nxt = db.scalar(
        select(Reservation)
        .where(Reservation.book_id == copy.book_id, Reservation.status == ReservationStatus.WAITING)
        .order_by(Reservation.created_at, Reservation.id)
        .with_for_update(skip_locked=True, of=Reservation)
        .limit(1)
    )
    if nxt is None:
        copy.status = CopyStatus.AVAILABLE
        return None
    copy.status = CopyStatus.ON_HOLD
    nxt.status = ReservationStatus.READY
    nxt.copy_id = copy.id
    nxt.ready_at = clock.now()
    nxt.expires_on = clock.today() + timedelta(days=settings.hold_pickup_days)
    notify(
        db,
        nxt.user_id,
        "hold_ready",
        "Your reserved book is ready",
        f"'{copy.book.title}' is waiting for you at the desk (copy {copy.barcode}). "
        f"Please collect it by {nxt.expires_on.isoformat()}.",
    )
    audit(db, actor, "hold.ready", "reservation", nxt.id, f"{copy.barcode} for user {nxt.user_id}")
    return nxt


# ---------------------------------------------------------------- issue
def checkout(
    db: Session,
    actor: User,
    member_ref: str | int,
    *,
    barcode: str | None = None,
    book_id: int | None = None,
    due_date: date | None = None,
) -> Loan:
    member = resolve_member(db, member_ref)
    check = eligibility(db, member)
    if not check.can_borrow:
        raise LibraryError("Cannot issue: " + "; ".join(check.reasons))
    if not barcode and not book_id:
        raise LibraryError("Provide a copy barcode or a book id")

    copy: BookCopy | None
    if barcode:
        copy = db.scalar(
            select(BookCopy).where(BookCopy.barcode == barcode.strip()).with_for_update(of=BookCopy)
        )
        if copy is None:
            raise NotFound(f"No copy with barcode '{barcode}'")
    else:
        assert book_id is not None
        get_or_404(db, Book, book_id, "Book")
        ready = db.scalar(
            select(Reservation).where(
                Reservation.book_id == book_id,
                Reservation.user_id == member.id,
                Reservation.status == ReservationStatus.READY,
            )
        )
        if ready and ready.copy_id:
            copy = db.scalar(
                select(BookCopy).where(BookCopy.id == ready.copy_id).with_for_update(of=BookCopy)
            )
        else:
            copy = db.scalar(
                select(BookCopy)
                .where(BookCopy.book_id == book_id, BookCopy.status == CopyStatus.AVAILABLE)
                .order_by(BookCopy.id)
                .with_for_update(skip_locked=True, of=BookCopy)
                .limit(1)
            )
        if copy is None:
            raise Conflict("No copies of this book are available - place a hold instead")

    held_for = None
    if copy.status == CopyStatus.ON_HOLD:
        held_for = db.scalar(
            select(Reservation).where(
                Reservation.copy_id == copy.id, Reservation.status == ReservationStatus.READY
            )
        )
        if held_for is None or held_for.user_id != member.id:
            raise Conflict(f"Copy {copy.barcode} is on the hold shelf for another member")
    elif copy.status != CopyStatus.AVAILABLE:
        raise Conflict(f"Copy {copy.barcode} is not available (status: {copy.status})")

    already = db.scalar(
        select(Loan.id)
        .join(BookCopy, Loan.copy_id == BookCopy.id)
        .where(
            Loan.user_id == member.id,
            Loan.status == LoanStatus.ACTIVE,
            BookCopy.book_id == copy.book_id,
        )
    )
    if already:
        raise Conflict("Member already has a copy of this book on loan")

    mt = member.membership_type
    assert mt is not None  # guaranteed by eligibility()
    today = clock.today()
    if due_date is not None and due_date < today:
        raise LibraryError("Due date cannot be in the past")
    loan = Loan(
        copy_id=copy.id,
        user_id=member.id,
        issued_by_id=actor.id,
        issued_at=clock.now(),
        due_date=due_date or today + timedelta(days=mt.loan_days),
        status=LoanStatus.ACTIVE,
        renew_count=0,
    )
    db.add(loan)
    copy.status = CopyStatus.ON_LOAN

    # Borrowing the book satisfies any hold this member had on it.
    res = held_for or _open_reservation(db, copy.book_id, member.id)
    if res is not None:
        _close_reservation(res, ReservationStatus.FULFILLED)

    db.flush()
    notify(
        db,
        member.id,
        "issued",
        "Book issued",
        f"'{copy.book.title}' ({copy.barcode}) is due on {loan.due_date.isoformat()}.",
    )
    audit(db, actor, "loan.issue", "loan", loan.id, f"{copy.barcode} -> {member.member_code}")
    db.refresh(loan)
    return loan


# ---------------------------------------------------------------- return
@dataclass
class ReturnResult:
    loan: Loan
    fines: list[Fine] = field(default_factory=list)
    hold: Reservation | None = None


def _lock_active_loan(db: Session, loan_id: int) -> Loan:
    loan = db.scalar(select(Loan).where(Loan.id == loan_id).with_for_update(of=Loan))
    if loan is None:
        raise NotFound("Loan not found")
    if loan.status != LoanStatus.ACTIVE:
        raise Conflict(f"Loan is already {loan.status}")
    return loan


def return_loan(
    db: Session,
    actor: User,
    loan_id: int,
    *,
    condition: str | None = None,
    damaged: bool = False,
    damage_fee: Decimal | None = None,
    notes: str | None = None,
) -> ReturnResult:
    loan = _lock_active_loan(db, loan_id)
    result = ReturnResult(loan=loan)
    days = overdue_days(loan)
    late_fee = money(days * fine_rate(loan.user))

    loan.status = LoanStatus.RETURNED
    loan.returned_at = clock.now()
    if notes:
        loan.notes = notes
    copy = loan.copy
    if condition:
        copy.condition = condition

    if late_fee > 0:
        result.fines.append(
            Fine(
                user_id=loan.user_id,
                loan_id=loan.id,
                amount=late_fee,
                reason=FineReason.OVERDUE,
                note=f"Returned {days} day(s) late",
            )
        )
    if damaged:
        copy.status = CopyStatus.DAMAGED
        copy.condition = "damaged"
        if damage_fee:
            result.fines.append(
                Fine(
                    user_id=loan.user_id,
                    loan_id=loan.id,
                    amount=money(damage_fee),
                    reason=FineReason.DAMAGED,
                    note=notes or "Damaged on return",
                )
            )
    else:
        result.hold = release_copy(db, copy, actor)

    for fine in result.fines:
        db.add(fine)
    total = sum((f.amount for f in result.fines), Decimal("0"))
    msg = f"Thanks for returning '{copy.book.title}'."
    if total:
        msg += f" A fine of ₹{total} has been added to your account."
    notify(db, loan.user_id, "returned", "Book returned", msg)
    audit(db, actor, "loan.return", "loan", loan.id, f"{copy.barcode}; fines ₹{total}")
    db.flush()
    return result


def checkin_by_barcode(db: Session, actor: User, barcode: str, **kwargs: object) -> ReturnResult:
    loan_id = db.scalar(
        select(Loan.id)
        .join(BookCopy, Loan.copy_id == BookCopy.id)
        .where(BookCopy.barcode == barcode.strip(), Loan.status == LoanStatus.ACTIVE)
    )
    if loan_id is None:
        raise NotFound(f"No active loan for barcode '{barcode}'")
    return return_loan(db, actor, loan_id, **kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------- renew
def renew(db: Session, actor: User, loan_id: int) -> Loan:
    loan = _lock_active_loan(db, loan_id)
    if not actor.is_staff and loan.user_id != actor.id:
        raise Forbidden("You can only renew your own loans")
    member = loan.user
    mt = member.membership_type
    if mt is None:
        raise LibraryError("Member has no membership plan")
    if overdue_days(loan) > 0:
        raise LibraryError("Overdue items cannot be renewed - please return it")
    if loan.renew_count >= mt.max_renewals:
        raise LibraryError(f"Renewal limit reached ({mt.max_renewals})")
    if member.membership_expiry and member.membership_expiry < clock.today():
        raise LibraryError("Membership has expired")
    waiting = db.scalar(
        select(func.count()).where(
            Reservation.book_id == loan.copy.book_id,
            Reservation.status == ReservationStatus.WAITING,
        )
    )
    if waiting:
        raise Conflict("Other members are waiting for this book - it cannot be renewed")
    loan.renew_count += 1
    loan.due_date = max(loan.due_date, clock.today()) + timedelta(days=mt.loan_days)
    audit(db, actor, "loan.renew", "loan", loan.id, f"new due {loan.due_date.isoformat()}")
    db.flush()
    return loan


# ---------------------------------------------------------------- lost
def mark_lost(db: Session, actor: User, loan_id: int) -> ReturnResult:
    loan = _lock_active_loan(db, loan_id)
    copy = loan.copy
    replacement = copy.price or settings.lost_book_default_price
    amount = money(replacement + settings.lost_book_processing_fee)
    late = money(overdue_days(loan) * fine_rate(loan.user))
    loan.status = LoanStatus.LOST
    loan.returned_at = clock.now()
    copy.status = CopyStatus.LOST
    result = ReturnResult(loan=loan)
    result.fines.append(
        Fine(
            user_id=loan.user_id,
            loan_id=loan.id,
            amount=amount,
            reason=FineReason.LOST,
            note=f"Replacement ₹{replacement} + processing ₹{settings.lost_book_processing_fee}",
        )
    )
    if late > 0:
        result.fines.append(
            Fine(
                user_id=loan.user_id,
                loan_id=loan.id,
                amount=late,
                reason=FineReason.OVERDUE,
                note="Overdue charges up to the date reported lost",
            )
        )
    for fine in result.fines:
        db.add(fine)
    notify(
        db,
        loan.user_id,
        "lost",
        "Book marked as lost",
        f"'{copy.book.title}' was marked lost. Charges of ₹{amount + late} were added.",
    )
    audit(db, actor, "loan.lost", "loan", loan.id, copy.barcode)
    db.flush()
    return result


# ---------------------------------------------------------------- reservations
def place_hold(db: Session, actor: User, book_id: int, member_id: int | None = None) -> Reservation:
    if member_id is not None and member_id != actor.id and not actor.is_staff:
        raise Forbidden("You can only place holds for yourself")
    member = get_or_404(db, User, member_id or actor.id, "Member")
    book = get_or_404(db, Book, book_id, "Book")
    if not member.is_active:
        raise LibraryError("Account is deactivated")
    if member.membership_expiry and member.membership_expiry < clock.today():
        raise LibraryError("Membership has expired")
    if _open_reservation(db, book_id, member.id):
        raise Conflict("You already have an active hold on this book")
    on_loan = db.scalar(
        select(Loan.id)
        .join(BookCopy, Loan.copy_id == BookCopy.id)
        .where(
            Loan.user_id == member.id,
            Loan.status == LoanStatus.ACTIVE,
            BookCopy.book_id == book_id,
        )
    )
    if on_loan:
        raise Conflict("You already have this book on loan")
    available = db.scalar(
        select(func.count()).where(
            BookCopy.book_id == book_id, BookCopy.status == CopyStatus.AVAILABLE
        )
    )
    if available:
        raise Conflict(f"{available} copy(ies) are on the shelf - borrow it directly at the desk")
    in_collection = db.scalar(
        select(func.count()).where(
            BookCopy.book_id == book_id,
            BookCopy.status.notin_([CopyStatus.LOST, CopyStatus.WITHDRAWN]),
        )
    )
    if not in_collection:
        raise Conflict("This title has no circulating copies")
    res = Reservation(book_id=book.id, user_id=member.id, status=ReservationStatus.WAITING)
    db.add(res)
    db.flush()
    audit(db, actor, "hold.place", "reservation", res.id, f"'{book.title}' for {member.name}")
    db.refresh(res)
    return res


def cancel_hold(db: Session, actor: User, reservation_id: int) -> Reservation:
    res = get_or_404(db, Reservation, reservation_id, "Reservation")
    if not actor.is_staff and res.user_id != actor.id:
        raise Forbidden("You can only cancel your own holds")
    if res.status not in (ReservationStatus.WAITING, ReservationStatus.READY):
        raise Conflict(f"Reservation is already {res.status}")
    copy = res.copy if res.status == ReservationStatus.READY else None
    _close_reservation(res, ReservationStatus.CANCELLED)
    if copy is not None:
        db.flush()
        release_copy(db, copy, actor)
    audit(db, actor, "hold.cancel", "reservation", res.id)
    db.flush()
    return res


# ---------------------------------------------------------------- fines
def settle_fine(db: Session, actor: User, fine_id: int, waive: bool, note: str | None) -> Fine:
    fine = db.scalar(select(Fine).where(Fine.id == fine_id).with_for_update(of=Fine))
    if fine is None:
        raise NotFound("Fine not found")
    if waive and not actor.is_staff:
        raise Forbidden("Only library staff can waive fines")
    if not actor.is_staff and fine.user_id != actor.id:
        raise Forbidden("You can only pay your own fines")
    if fine.status != FineStatus.UNPAID:
        raise Conflict(f"Fine is already {fine.status}")
    fine.status = FineStatus.WAIVED if waive else FineStatus.PAID
    fine.settled_at = clock.now()
    fine.settled_by_id = actor.id
    if note:
        fine.note = f"{fine.note or ''} | {note}".strip(" |")
    audit(db, actor, "fine.waive" if waive else "fine.pay", "fine", fine.id, f"₹{fine.amount}")
    db.flush()
    return fine


# ---------------------------------------------------------------- daily jobs
def run_daily_jobs(db: Session) -> dict[str, int]:
    """Expire uncollected holds and send due-soon / overdue reminders (idempotent per day)."""
    today = clock.today()
    expired = 0
    stale = db.scalars(
        select(Reservation).where(
            Reservation.status == ReservationStatus.READY, Reservation.expires_on < today
        )
    ).all()
    for res in stale:
        copy = res.copy
        _close_reservation(res, ReservationStatus.EXPIRED)
        notify(
            db,
            res.user_id,
            "hold_expired",
            "Hold expired",
            f"Your hold on '{res.book.title}' expired because it was not collected in time.",
        )
        db.flush()
        if copy is not None:
            release_copy(db, copy, None)
        expired += 1

    due_soon = 0
    soon = db.scalars(
        select(Loan).where(
            Loan.status == LoanStatus.ACTIVE,
            Loan.due_date >= today,
            Loan.due_date <= today + timedelta(days=settings.due_soon_days),
        )
    ).all()
    for loan in soon:
        due_soon += notify(
            db,
            loan.user_id,
            "due_soon",
            "Book due soon",
            f"'{loan.copy.book.title}' is due on {loan.due_date.isoformat()}. "
            "Renew it online or return it to avoid fines.",
            ref_key=f"due:{loan.id}:{loan.due_date.isoformat()}",
        )

    overdue = 0
    late = db.scalars(
        select(Loan).where(Loan.status == LoanStatus.ACTIVE, Loan.due_date < today)
    ).all()
    for loan in late:
        overdue += notify(
            db,
            loan.user_id,
            "overdue",
            "Book overdue",
            f"'{loan.copy.book.title}' was due on {loan.due_date.isoformat()} "
            f"({overdue_days(loan)} day(s) ago). Fine so far: ₹{money(accrued_fine(loan))}.",
            ref_key=f"overdue:{loan.id}:{today.isoformat()}",
        )
    db.flush()
    return {"expired_holds": expired, "due_soon_notices": due_soon, "overdue_notices": overdue}
