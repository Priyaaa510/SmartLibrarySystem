from fastapi import APIRouter
from sqlalchemy import Integer, String, case, cast, func, or_, select

from .. import clock
from ..errors import Conflict, Forbidden, LibraryError
from ..models import Fine, FineStatus, Loan, LoanStatus, MembershipType, Reservation, Role, User
from ..schemas import (
    MemberCreate,
    MemberDetail,
    MembershipTypeIn,
    MembershipTypeOut,
    MemberSummary,
    MemberUpdate,
    Message,
    Page,
    UserOut,
)
from ..security import DB, Admin, Staff
from ..services.circulation import eligibility, fine_out, loan_out, reservation_out
from ..services.common import audit, get_or_404, notify, paginate_args
from ..services.members import create_user, ensure_email_free, renew_membership

router = APIRouter(prefix="/api", tags=["members"])


# ---------------------------------------------------------------- membership plans
@router.get("/membership-types", response_model=list[MembershipTypeOut])
def list_plans(db: DB) -> list[MembershipType]:
    return list(db.scalars(select(MembershipType).order_by(MembershipType.id)))


@router.post("/membership-types", response_model=MembershipTypeOut, status_code=201)
def create_plan(data: MembershipTypeIn, db: DB, admin: Admin) -> MembershipType:
    if db.scalar(select(MembershipType.id).where(MembershipType.name == data.name)):
        raise Conflict("A plan with this name already exists")
    plan = MembershipType(**data.model_dump())
    db.add(plan)
    db.flush()
    audit(db, admin, "plan.create", "membership_type", plan.id, plan.name)
    db.commit()
    return plan


@router.put("/membership-types/{plan_id}", response_model=MembershipTypeOut)
def update_plan(plan_id: int, data: MembershipTypeIn, db: DB, admin: Admin) -> MembershipType:
    plan = get_or_404(db, MembershipType, plan_id, "Membership plan")
    for key, value in data.model_dump().items():
        setattr(plan, key, value)
    audit(db, admin, "plan.update", "membership_type", plan.id, plan.name)
    db.commit()
    return plan


# ---------------------------------------------------------------- members
@router.get("/members", response_model=Page[MemberSummary])
def list_members(
    db: DB,
    staff: Staff,
    q: str = "",
    role: str | None = "member",
    status: str | None = None,
    page: int = 1,
    size: int = 20,
) -> Page[MemberSummary]:
    page, size = paginate_args(page, size)
    today = clock.today()
    loans = (
        select(
            Loan.user_id.label("uid"),
            func.count().label("active"),
            func.sum(case((Loan.due_date < today, 1), else_=0)).label("overdue"),
        )
        .where(Loan.status == LoanStatus.ACTIVE)
        .group_by(Loan.user_id)
        .subquery()
    )
    fines = (
        select(Fine.user_id.label("uid"), func.sum(Fine.amount).label("unpaid"))
        .where(Fine.status == FineStatus.UNPAID)
        .group_by(Fine.user_id)
        .subquery()
    )
    stmt = (
        select(
            User,
            func.coalesce(loans.c.active, 0),
            cast(func.coalesce(loans.c.overdue, 0), Integer),
            func.coalesce(fines.c.unpaid, 0),
        )
        .outerjoin(loans, loans.c.uid == User.id)
        .outerjoin(fines, fines.c.uid == User.id)
    )
    if role and role != "all":
        stmt = stmt.where(User.role == role)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                User.name.ilike(like),
                User.email.ilike(like),
                User.member_code.ilike(like),
                User.phone.ilike(like),
                cast(User.id, String) == q.strip(),
            )
        )
    if status == "active":
        stmt = stmt.where(
            User.is_active.is_(True),
            or_(User.membership_expiry.is_(None), User.membership_expiry >= today),
        )
    elif status == "expired":
        stmt = stmt.where(User.membership_expiry < today)
    elif status == "inactive":
        stmt = stmt.where(User.is_active.is_(False))
    elif status == "overdue":
        stmt = stmt.where(loans.c.overdue > 0)
    elif status == "fines":
        stmt = stmt.where(fines.c.unpaid > 0)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(User.name).offset((page - 1) * size).limit(size)).all()
    items = [
        MemberSummary(
            **UserOut.model_validate(u).model_dump(),
            active_loans=active,
            overdue_loans=overdue,
            unpaid_fines=float(unpaid),
        )
        for u, active, overdue, unpaid in rows
    ]
    return Page(items=items, total=total, page=page, size=size)


@router.post("/members", response_model=UserOut, status_code=201)
def create_member(data: MemberCreate, db: DB, staff: Staff) -> User:
    if data.role != Role.MEMBER and staff.role != Role.ADMIN:
        raise Forbidden("Only administrators can create staff accounts")
    user = create_user(db, **data.model_dump())
    notify(
        db,
        user.id,
        "welcome",
        "Welcome to Smart Library",
        f"Your account was created by the library. Your member code is {user.member_code}.",
    )
    audit(db, staff, "member.create", "user", user.id, f"{user.member_code} {user.name}")
    db.commit()
    return user


@router.get("/members/{member_id}", response_model=MemberDetail)
def member_detail(member_id: int, db: DB, staff: Staff) -> MemberDetail:
    member = get_or_404(db, User, member_id, "Member")
    loans = db.scalars(
        select(Loan)
        .where(Loan.user_id == member_id)
        .order_by((Loan.status == LoanStatus.ACTIVE).desc(), Loan.issued_at.desc())
        .limit(100)
    ).all()
    reservations = db.scalars(
        select(Reservation)
        .where(Reservation.user_id == member_id)
        .order_by(Reservation.created_at.desc())
        .limit(50)
    ).all()
    fines = db.scalars(
        select(Fine).where(Fine.user_id == member_id).order_by(Fine.created_at.desc())
    ).all()
    return MemberDetail(
        member=UserOut.model_validate(member),
        eligibility=eligibility(db, member),
        loans=[loan_out(x) for x in loans],
        reservations=[reservation_out(db, r) for r in reservations],
        fines=[fine_out(f) for f in fines],
    )


@router.put("/members/{member_id}", response_model=UserOut)
def update_member(member_id: int, data: MemberUpdate, db: DB, staff: Staff) -> User:
    member = get_or_404(db, User, member_id, "Member")
    changes = data.model_dump(exclude_unset=True)
    if ("role" in changes or member.is_staff) and staff.role != Role.ADMIN:
        raise Forbidden("Only administrators can manage staff accounts")
    if member.id == staff.id and changes.get("is_active") is False:
        raise LibraryError("You cannot deactivate your own account")
    if "email" in changes:
        ensure_email_free(db, changes["email"], exclude_id=member.id)
        changes["email"] = changes["email"].lower()
    if changes.get("membership_type_id") is not None:
        get_or_404(db, MembershipType, changes["membership_type_id"], "Membership plan")
    for key, value in changes.items():
        setattr(member, key, value)
    audit(db, staff, "member.update", "user", member.id, ", ".join(changes))
    db.commit()
    db.refresh(member)
    return member


@router.post("/members/{member_id}/renew-membership", response_model=UserOut)
def renew(member_id: int, db: DB, staff: Staff) -> User:
    member = renew_membership(db, get_or_404(db, User, member_id, "Member"))
    assert member.membership_expiry is not None
    notify(
        db,
        member.id,
        "membership",
        "Membership renewed",
        f"Your membership is now valid until {member.membership_expiry.isoformat()}.",
    )
    audit(db, staff, "member.renew", "user", member.id, str(member.membership_expiry))
    db.commit()
    return member


@router.delete("/members/{member_id}", response_model=Message)
def deactivate_member(member_id: int, db: DB, staff: Staff) -> Message:
    """Members are never hard-deleted (their circulation history must be kept)."""
    member = get_or_404(db, User, member_id, "Member")
    if member.is_staff and staff.role != Role.ADMIN:
        raise Forbidden("Only administrators can manage staff accounts")
    if member.id == staff.id:
        raise LibraryError("You cannot deactivate your own account")
    active = db.scalar(
        select(func.count(Loan.id)).where(
            Loan.user_id == member_id, Loan.status == LoanStatus.ACTIVE
        )
    )
    if active:
        raise Conflict(f"Member still has {active} book(s) on loan")
    member.is_active = False
    audit(db, staff, "member.deactivate", "user", member.id, member.name)
    db.commit()
    return Message(detail=f"{member.name} has been deactivated")
