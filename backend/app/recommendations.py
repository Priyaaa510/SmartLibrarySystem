"""Book recommendations implemented with the Strategy pattern."""

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from .models import Book, BookCopy, Category, Loan, Reservation, ReservationStatus, User
from .schemas import BookSummary
from .services.catalog import book_select, to_summary


def borrowed_book_ids(db: Session, member: User) -> set[int]:
    """Books the member has borrowed before or is currently waiting for."""
    rows = db.scalars(
        select(BookCopy.book_id)
        .join(Loan, Loan.copy_id == BookCopy.id)
        .where(Loan.user_id == member.id)
    )
    held = db.scalars(
        select(Reservation.book_id).where(
            Reservation.user_id == member.id,
            Reservation.status.in_([ReservationStatus.WAITING, ReservationStatus.READY]),
        )
    )
    return set(rows) | set(held)


class RecommendationStrategy(ABC):
    name: str = ""
    description: str = ""

    def recommend(self, db: Session, member: User, limit: int = 8) -> list[BookSummary]:
        stmt, cols = book_select()
        exclude = borrowed_book_ids(db, member)
        if exclude:
            stmt = stmt.where(Book.id.notin_(exclude))
        filtered = self.filter(db, member, stmt, cols)
        if filtered is None:
            return []
        rows = db.execute(
            filtered.order_by(
                (cols["available"] > 0).desc(),
                *self.ranking(cols),
                Book.title,
            ).limit(limit)
        ).all()
        return [to_summary(r) for r in rows]

    def ranking(self, cols: dict[str, Any]) -> list[Any]:
        return [cols["avg_rating"].desc().nulls_last(), cols["times_borrowed"].desc()]

    @abstractmethod
    def filter(
        self, db: Session, member: User, stmt: Select[Any], cols: dict[str, Any]
    ) -> Select[Any] | None:
        """Narrow the candidate books; return None when there is nothing to recommend."""


class CategoryRecommendation(RecommendationStrategy):
    name = "category"
    description = "Books from the categories you selected in your profile"

    def filter(self, db, member, stmt, cols):  # type: ignore[no-untyped-def]
        if not member.preferred_categories:
            return None
        return stmt.where(Book.category.has(Category.name.in_(member.preferred_categories)))


class HistoryRecommendation(RecommendationStrategy):
    name = "history"
    description = "Similar categories and authors to what you have borrowed before"

    def filter(self, db, member, stmt, cols):  # type: ignore[no-untyped-def]
        history = (
            select(Book.category_id, Book.author)
            .join(BookCopy, BookCopy.book_id == Book.id)
            .join(Loan, Loan.copy_id == BookCopy.id)
            .where(Loan.user_id == member.id)
        )
        rows = db.execute(history).all()
        if not rows:
            return None
        cats = {r.category_id for r in rows}
        authors = {r.author for r in rows}
        return stmt.where(Book.category_id.in_(cats) | Book.author.in_(authors))


class PopularRecommendation(RecommendationStrategy):
    name = "popular"
    description = "The most borrowed and best rated books in the library"

    def ranking(self, cols):  # type: ignore[no-untyped-def]
        return [cols["times_borrowed"].desc(), cols["avg_rating"].desc().nulls_last()]

    def filter(self, db, member, stmt, cols):  # type: ignore[no-untyped-def]
        return stmt


class HybridRecommendation(RecommendationStrategy):
    """Blends the other strategies: profile picks, then history, then popular titles."""

    name = "hybrid"
    description = "A blend of your interests, history and what's popular"
    parts: tuple[RecommendationStrategy, ...] = (
        CategoryRecommendation(),
        HistoryRecommendation(),
        PopularRecommendation(),
    )

    def recommend(self, db: Session, member: User, limit: int = 8) -> list[BookSummary]:
        seen: dict[int, BookSummary] = {}
        for strategy in self.parts:
            for book in strategy.recommend(db, member, limit):
                seen.setdefault(book.id, book)
            if len(seen) >= limit:
                break
        return list(seen.values())[:limit]

    def filter(self, db, member, stmt, cols):  # type: ignore[no-untyped-def]
        return stmt


STRATEGIES: dict[str, RecommendationStrategy] = {
    s.name: s
    for s in (
        HybridRecommendation(),
        CategoryRecommendation(),
        HistoryRecommendation(),
        PopularRecommendation(),
    )
}


def similar_books(db: Session, book: Book, limit: int = 6) -> list[BookSummary]:
    stmt, cols = book_select()
    stmt = stmt.where(
        Book.id != book.id,
        (Book.category_id == book.category_id) | (Book.author == book.author),
    ).order_by(
        (Book.author == book.author).desc(),
        cols["avg_rating"].desc().nulls_last(),
        cols["times_borrowed"].desc(),
    )
    return [to_summary(r) for r in db.execute(stmt.limit(limit)).all()]
