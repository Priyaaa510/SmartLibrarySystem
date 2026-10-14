"""Catalog queries: books enriched with copy availability, ratings and popularity."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from ..models import (
    Book,
    BookCopy,
    Category,
    CopyStatus,
    Loan,
    Reservation,
    ReservationStatus,
    Review,
)
from ..schemas import BookDetail, BookSummary, CopyOut, ReviewOut

# Copies that are still part of the collection (count towards "total copies").
IN_COLLECTION = [s for s in CopyStatus if s not in (CopyStatus.LOST, CopyStatus.WITHDRAWN)]

SORTS = {"title", "newest", "popular", "rating", "author", "year"}


def _stats_subqueries() -> tuple[Any, Any, Any]:
    copies = (
        select(
            BookCopy.book_id.label("book_id"),
            func.count().filter(BookCopy.status.in_(IN_COLLECTION)).label("total"),
            func.count().filter(BookCopy.status == CopyStatus.AVAILABLE).label("available"),
        )
        .group_by(BookCopy.book_id)
        .subquery()
    )
    ratings = (
        select(
            Review.book_id.label("book_id"),
            func.avg(Review.rating).label("avg_rating"),
            func.count().label("review_count"),
        )
        .group_by(Review.book_id)
        .subquery()
    )
    borrowed = (
        select(BookCopy.book_id.label("book_id"), func.count(Loan.id).label("times_borrowed"))
        .join(Loan, Loan.copy_id == BookCopy.id)
        .group_by(BookCopy.book_id)
        .subquery()
    )
    return copies, ratings, borrowed


def book_select() -> tuple[Select[Any], dict[str, Any]]:
    copies, ratings, borrowed = _stats_subqueries()
    cols = {
        "total": func.coalesce(copies.c.total, 0),
        "available": func.coalesce(copies.c.available, 0),
        "avg_rating": ratings.c.avg_rating,
        "review_count": func.coalesce(ratings.c.review_count, 0),
        "times_borrowed": func.coalesce(borrowed.c.times_borrowed, 0),
    }
    stmt = (
        select(Book, *[c.label(k) for k, c in cols.items()])
        .outerjoin(copies, copies.c.book_id == Book.id)
        .outerjoin(ratings, ratings.c.book_id == Book.id)
        .outerjoin(borrowed, borrowed.c.book_id == Book.id)
    )
    return stmt, cols


def to_summary(row: Any) -> BookSummary:
    book: Book = row[0]
    summary = BookSummary.model_validate(book)
    summary.total_copies = row.total
    summary.available_copies = row.available
    summary.avg_rating = round(float(row.avg_rating), 2) if row.avg_rating is not None else None
    summary.review_count = row.review_count
    summary.times_borrowed = row.times_borrowed
    return summary


def search_books(
    db: Session,
    *,
    q: str = "",
    category_id: int | None = None,
    category: str | None = None,
    language: str | None = None,
    available_only: bool = False,
    sort: str = "title",
    page: int = 1,
    size: int = 20,
) -> tuple[list[BookSummary], int]:
    stmt, cols = book_select()
    q = q.strip()
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Book.title.ilike(like),
                Book.author.ilike(like),
                Book.isbn.ilike(like),
                Book.publisher.ilike(like),
                Book.category.has(Category.name.ilike(like)),
            )
        )
    if category_id:
        stmt = stmt.where(Book.category_id == category_id)
    if category:
        stmt = stmt.where(Book.category.has(Category.name == category))
    if language:
        stmt = stmt.where(Book.language == language)
    if available_only:
        stmt = stmt.where(cols["available"] > 0)

    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0

    orders: dict[str, list[Any]] = {
        "title": [Book.title.asc()],
        "author": [Book.author.asc(), Book.title.asc()],
        "newest": [Book.created_at.desc(), Book.id.desc()],
        "year": [Book.published_year.desc().nulls_last(), Book.title.asc()],
        "popular": [cols["times_borrowed"].desc(), Book.title.asc()],
        "rating": [cols["avg_rating"].desc().nulls_last(), Book.title.asc()],
    }
    order = orders.get(sort, orders["title"])
    rows = db.execute(stmt.order_by(*order).offset((page - 1) * size).limit(size)).all()
    return [to_summary(r) for r in rows], total


def summaries_for(db: Session, book_ids: Sequence[int]) -> dict[int, BookSummary]:
    if not book_ids:
        return {}
    stmt, _ = book_select()
    rows = db.execute(stmt.where(Book.id.in_(book_ids))).all()
    return {r[0].id: to_summary(r) for r in rows}


def review_out(review: Review) -> ReviewOut:
    return ReviewOut(
        id=review.id,
        book_id=review.book_id,
        user_id=review.user_id,
        rating=review.rating,
        comment=review.comment,
        created_at=review.created_at,
        reviewer=review.user.name,
    )


def book_detail(db: Session, book: Book) -> BookDetail:
    summary = summaries_for(db, [book.id])[book.id]
    holds = db.scalar(
        select(func.count()).where(
            Reservation.book_id == book.id, Reservation.status == ReservationStatus.WAITING
        )
    )
    reviews = db.scalars(
        select(Review).where(Review.book_id == book.id).order_by(Review.created_at.desc())
    ).all()
    return BookDetail(
        **summary.model_dump(),
        edition=book.edition,
        pages=book.pages,
        description=book.description,
        created_at=book.created_at,
        copies=[CopyOut.model_validate(c) for c in book.copies],
        holds_waiting=holds or 0,
        reviews=[review_out(r) for r in reviews],
    )


def next_barcode(db: Session, book: Book) -> str:
    """Barcodes look like BK00012-003 (book id, copy sequence)."""
    existing = db.scalar(select(func.count()).where(BookCopy.book_id == book.id)) or 0
    seq = existing + 1
    while True:
        code = f"BK{book.id:05d}-{seq:03d}"
        if not db.scalar(select(BookCopy.id).where(BookCopy.barcode == code)):
            return code
        seq += 1
