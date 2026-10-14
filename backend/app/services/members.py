import calendar
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import clock
from ..errors import Conflict, LibraryError
from ..models import MembershipType, Role, User
from ..security import hash_password

DEFAULT_PLAN = "Student"


def add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def ensure_email_free(db: Session, email: str, exclude_id: int | None = None) -> None:
    stmt = select(User.id).where(func.lower(User.email) == email.lower())
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
    if db.scalar(stmt):
        raise Conflict("An account with this email already exists")


def create_user(
    db: Session,
    *,
    name: str,
    email: str,
    password: str,
    role: str = Role.MEMBER,
    phone: str | None = None,
    address: str | None = None,
    preferred_categories: list[str] | None = None,
    membership_type_id: int | None = None,
) -> User:
    ensure_email_free(db, email)
    plan: MembershipType | None = None
    if membership_type_id is not None:
        plan = db.get(MembershipType, membership_type_id)
        if plan is None:
            raise LibraryError("Membership plan not found")
    elif role == Role.MEMBER:
        plan = db.scalar(select(MembershipType).where(MembershipType.name == DEFAULT_PLAN))
    if plan is None and role != Role.MEMBER:
        # Staff can borrow too, using the most generous plan available.
        plan = db.scalar(select(MembershipType).order_by(MembershipType.max_books.desc()))
    user = User(
        name=name.strip(),
        email=email.lower(),
        password_hash=hash_password(password),
        role=role,
        phone=phone,
        address=address,
        preferred_categories=preferred_categories or [],
        membership_type_id=plan.id if plan else None,
        membership_expiry=add_months(clock.today(), plan.validity_months) if plan else None,
        is_active=True,
    )
    db.add(user)
    db.flush()
    prefix = "LIB" if role == Role.MEMBER else "STF"
    user.member_code = f"{prefix}{user.id:06d}"
    db.flush()
    db.refresh(user)
    return user


def renew_membership(db: Session, member: User) -> User:
    plan = member.membership_type
    if plan is None:
        raise LibraryError("Member has no membership plan")
    base = max(member.membership_expiry or clock.today(), clock.today())
    member.membership_expiry = add_months(base, plan.validity_months)
    db.flush()
    return member
