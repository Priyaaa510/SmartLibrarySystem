"""Pydantic request/response schemas."""

from datetime import date, datetime
from decimal import Decimal
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int


class Message(BaseModel):
    detail: str


# ---------- membership & users ----------
class MembershipTypeIn(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    description: str = ""
    max_books: int = Field(ge=1, le=50)
    loan_days: int = Field(ge=1, le=180)
    max_renewals: int = Field(ge=0, le=10)
    fine_per_day: Decimal = Field(ge=0)
    max_unpaid_fine: Decimal = Field(ge=0)
    validity_months: int = Field(default=12, ge=1, le=120)


class MembershipTypeOut(ORM):
    id: int
    name: str
    description: str
    max_books: int
    loan_days: int
    max_renewals: int
    fine_per_day: float
    max_unpaid_fine: float
    validity_months: int


class UserOut(ORM):
    id: int
    member_code: str | None
    name: str
    email: str
    role: str
    phone: str | None
    address: str | None
    membership_type: MembershipTypeOut | None
    membership_expiry: date | None
    preferred_categories: list[str]
    is_active: bool
    created_at: datetime


class MemberSummary(UserOut):
    active_loans: int = 0
    overdue_loans: int = 0
    unpaid_fines: float = 0


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    phone: str | None = None
    address: str | None = None
    preferred_categories: list[str] = []


class MemberCreate(RegisterIn):
    role: Literal["member", "librarian", "admin"] = "member"
    membership_type_id: int | None = None


class MemberUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    email: EmailStr | None = None
    phone: str | None = None
    address: str | None = None
    preferred_categories: list[str] | None = None
    membership_type_id: int | None = None
    membership_expiry: date | None = None
    is_active: bool | None = None
    role: Literal["member", "librarian", "admin"] | None = None


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    phone: str | None = None
    address: str | None = None
    preferred_categories: list[str] | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- catalog ----------
class CategoryIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = ""


class CategoryOut(ORM):
    id: int
    name: str
    description: str


class CategoryWithCount(CategoryOut):
    book_count: int = 0


class BookBase(BaseModel):
    isbn: str = Field(min_length=3, max_length=20)
    title: str = Field(min_length=1, max_length=255)
    author: str = Field(min_length=1, max_length=255)
    publisher: str | None = None
    published_year: int | None = Field(default=None, ge=1000, le=2100)
    edition: str | None = None
    language: str = "English"
    pages: int | None = Field(default=None, ge=1)
    description: str | None = None
    cover_url: str | None = None
    shelf_location: str | None = None
    category_id: int


class BookCreate(BookBase):
    copies: int = Field(default=1, ge=0, le=100)
    price: Decimal | None = Field(default=None, ge=0)


class BookUpdate(BaseModel):
    isbn: str | None = Field(default=None, min_length=3, max_length=20)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    author: str | None = Field(default=None, min_length=1, max_length=255)
    publisher: str | None = None
    published_year: int | None = Field(default=None, ge=1000, le=2100)
    edition: str | None = None
    language: str | None = None
    pages: int | None = Field(default=None, ge=1)
    description: str | None = None
    cover_url: str | None = None
    shelf_location: str | None = None
    category_id: int | None = None


class BookSummary(ORM):
    id: int
    isbn: str
    title: str
    author: str
    publisher: str | None
    published_year: int | None
    language: str
    cover_url: str | None
    shelf_location: str | None
    category: CategoryOut
    total_copies: int = 0
    available_copies: int = 0
    avg_rating: float | None = None
    review_count: int = 0
    times_borrowed: int = 0


class CopyIn(BaseModel):
    count: int = Field(default=1, ge=1, le=100)
    price: Decimal | None = Field(default=None, ge=0)
    condition: str = "good"


class CopyUpdate(BaseModel):
    status: Literal["available", "maintenance", "damaged", "lost", "withdrawn"] | None = None
    condition: str | None = None
    price: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None


class CopyOut(ORM):
    id: int
    book_id: int
    barcode: str
    status: str
    condition: str
    acquired_on: date | None
    price: float | None
    notes: str | None


class CopyWithBook(CopyOut):
    book: BookSummary


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=2000)


class ReviewOut(ORM):
    id: int
    book_id: int
    user_id: int
    rating: int
    comment: str
    created_at: datetime
    reviewer: str


class BookDetail(BookSummary):
    edition: str | None
    pages: int | None
    description: str | None
    created_at: datetime
    copies: list[CopyOut]
    holds_waiting: int = 0
    reviews: list[ReviewOut] = []


# ---------- circulation ----------
class CheckoutIn(BaseModel):
    member: str = Field(description="Member id or member code, e.g. 3 or LIB000003")
    barcode: str | None = None
    book_id: int | None = None
    due_date: date | None = None


class ReturnIn(BaseModel):
    condition: str | None = None
    damaged: bool = False
    damage_fee: Decimal | None = Field(default=None, gt=0)
    notes: str | None = None


class CheckinIn(ReturnIn):
    barcode: str


class LoanOut(ORM):
    id: int
    status: str
    issued_at: datetime
    due_date: date
    returned_at: datetime | None
    renew_count: int
    max_renewals: int = 0
    is_overdue: bool = False
    overdue_days: int = 0
    accrued_fine: float = 0
    member_id: int
    member_name: str
    member_code: str | None
    copy_id: int
    barcode: str
    book_id: int
    book_title: str
    book_author: str
    cover_url: str | None = None


class ReturnOut(BaseModel):
    loan: LoanOut
    fines: list["FineOut"]
    hold_assigned_to: str | None = None


class ReservationIn(BaseModel):
    book_id: int
    member_id: int | None = None  # staff may place a hold on behalf of a member


class ReservationOut(BaseModel):
    id: int
    status: str
    created_at: datetime
    ready_at: datetime | None
    expires_on: date | None
    closed_at: datetime | None
    queue_position: int | None
    member_id: int
    member_name: str
    book_id: int
    book_title: str
    book_author: str
    barcode: str | None


class FineIn(BaseModel):
    member_id: int
    amount: Decimal = Field(gt=0)
    reason: Literal["overdue", "lost", "damaged", "other"] = "other"
    note: str | None = None


class FineSettle(BaseModel):
    note: str | None = None


class FineOut(BaseModel):
    id: int
    member_id: int
    member_name: str
    loan_id: int | None
    book_title: str | None
    amount: float
    reason: str
    status: str
    note: str | None
    created_at: datetime
    settled_at: datetime | None


class Eligibility(BaseModel):
    can_borrow: bool
    reasons: list[str]
    active_loans: int
    max_books: int
    unpaid_fines: float


class MemberDetail(BaseModel):
    member: UserOut
    eligibility: Eligibility
    loans: list[LoanOut]
    reservations: list[ReservationOut]
    fines: list[FineOut]


class MySummary(BaseModel):
    user: UserOut
    eligibility: Eligibility
    active_loans: list[LoanOut]
    reservations: list[ReservationOut]
    unpaid_fines: list[FineOut]
    total_borrowed: int
    unread_notifications: int


class NotificationOut(ORM):
    id: int
    kind: str
    title: str
    message: str
    is_read: bool
    created_at: datetime


class AuditOut(BaseModel):
    id: int
    actor: str | None
    action: str
    entity: str
    entity_id: int | None
    details: str
    created_at: datetime


class JobResult(BaseModel):
    expired_holds: int
    due_soon_notices: int
    overdue_notices: int


ReturnOut.model_rebuild()
