"""SQLAlchemy ORM models (PostgreSQL)."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Role(StrEnum):
    ADMIN = "admin"
    LIBRARIAN = "librarian"
    MEMBER = "member"


class CopyStatus(StrEnum):
    AVAILABLE = "available"
    ON_LOAN = "on_loan"
    ON_HOLD = "on_hold"  # set aside on the hold shelf for a member
    MAINTENANCE = "maintenance"
    DAMAGED = "damaged"
    LOST = "lost"
    WITHDRAWN = "withdrawn"


class LoanStatus(StrEnum):
    ACTIVE = "active"
    RETURNED = "returned"
    LOST = "lost"


class ReservationStatus(StrEnum):
    WAITING = "waiting"
    READY = "ready"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class FineStatus(StrEnum):
    UNPAID = "unpaid"
    PAID = "paid"
    WAIVED = "waived"


class FineReason(StrEnum):
    OVERDUE = "overdue"
    LOST = "lost"
    DAMAGED = "damaged"
    OTHER = "other"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MembershipType(Base):
    __tablename__ = "membership_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    max_books: Mapped[int] = mapped_column(Integer)
    loan_days: Mapped[int] = mapped_column(Integer)
    max_renewals: Mapped[int] = mapped_column(Integer)
    fine_per_day: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    max_unpaid_fine: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    validity_months: Mapped[int] = mapped_column(Integer, default=12)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_code: Mapped[str | None] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=Role.MEMBER)
    phone: Mapped[str | None] = mapped_column(String(30))
    address: Mapped[str | None] = mapped_column(String(255))
    membership_type_id: Mapped[int | None] = mapped_column(ForeignKey("membership_types.id"))
    membership_expiry: Mapped[date | None] = mapped_column(Date)
    preferred_categories: Mapped[list[str]] = mapped_column(
        ARRAY(String(80)), default=list, server_default="{}"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    membership_type: Mapped[MembershipType | None] = relationship(lazy="joined")

    @property
    def is_staff(self) -> bool:
        return self.role in (Role.ADMIN, Role.LIBRARIAN)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str] = mapped_column(String(255), default="")


class Book(TimestampMixin, Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)
    isbn: Mapped[str] = mapped_column(String(20), unique=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    author: Mapped[str] = mapped_column(String(255), index=True)
    publisher: Mapped[str | None] = mapped_column(String(255))
    published_year: Mapped[int | None] = mapped_column(Integer)
    edition: Mapped[str | None] = mapped_column(String(50))
    language: Mapped[str] = mapped_column(String(40), default="English")
    pages: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    cover_url: Mapped[str | None] = mapped_column(String(500))
    shelf_location: Mapped[str | None] = mapped_column(String(50))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))

    category: Mapped[Category] = relationship(lazy="joined")
    copies: Mapped[list["BookCopy"]] = relationship(
        back_populates="book", cascade="all, delete-orphan", order_by="BookCopy.id"
    )


class BookCopy(Base):
    __tablename__ = "book_copies"
    __table_args__ = (Index("ix_book_copies_book_status", "book_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"))
    barcode: Mapped[str] = mapped_column(String(40), unique=True)
    status: Mapped[str] = mapped_column(String(20), default=CopyStatus.AVAILABLE)
    condition: Mapped[str] = mapped_column(String(20), default="good")
    acquired_on: Mapped[date | None] = mapped_column(Date)
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    notes: Mapped[str | None] = mapped_column(String(255))

    book: Mapped[Book] = relationship(back_populates="copies", lazy="joined")


class Loan(Base):
    __tablename__ = "loans"
    __table_args__ = (
        Index("ix_loans_user_status", "user_id", "status"),
        # A physical copy can only be out on one active loan at a time.
        Index(
            "uq_loans_active_copy",
            "copy_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    copy_id: Mapped[int] = mapped_column(ForeignKey("book_copies.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    issued_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due_date: Mapped[date] = mapped_column(Date)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    renew_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default=LoanStatus.ACTIVE)
    notes: Mapped[str | None] = mapped_column(String(255))

    copy: Mapped[BookCopy] = relationship(lazy="joined")
    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="joined")


class Reservation(TimestampMixin, Base):
    __tablename__ = "reservations"
    __table_args__ = (
        Index(
            "uq_reservations_open_per_member",
            "book_id",
            "user_id",
            unique=True,
            postgresql_where=text("status IN ('waiting', 'ready')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    copy_id: Mapped[int | None] = mapped_column(ForeignKey("book_copies.id"))
    status: Mapped[str] = mapped_column(String(20), default=ReservationStatus.WAITING)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_on: Mapped[date | None] = mapped_column(Date)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    book: Mapped[Book] = relationship(lazy="joined")
    user: Mapped[User] = relationship(lazy="joined")
    copy: Mapped[BookCopy | None] = relationship(lazy="joined")


class Fine(TimestampMixin, Base):
    __tablename__ = "fines"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_fines_amount_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    loan_id: Mapped[int | None] = mapped_column(ForeignKey("loans.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    reason: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default=FineStatus.UNPAID)
    note: Mapped[str | None] = mapped_column(String(255))
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    settled_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="joined")
    loan: Mapped[Loan | None] = relationship(lazy="joined")


class Review(TimestampMixin, Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("book_id", "user_id", name="uq_reviews_book_user"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_reviews_rating"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(Text, default="")

    user: Mapped[User] = relationship(lazy="joined")


class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("user_id", "ref_key", name="uq_notifications_ref"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(150))
    message: Mapped[str] = mapped_column(String(500))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    # De-duplication key for scheduled reminders, e.g. "overdue:12:2026-10-09"
    ref_key: Mapped[str | None] = mapped_column(String(80))


class AuditLog(TimestampMixin, Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(50), index=True)
    entity: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[str] = mapped_column(String(500), default="")

    actor: Mapped[User | None] = relationship(lazy="joined")
