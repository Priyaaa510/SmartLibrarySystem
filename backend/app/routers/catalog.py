from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from .. import clock
from ..errors import Conflict, Forbidden, LibraryError, NotFound
from ..models import Book, BookCopy, Category, CopyStatus, Loan, Review
from ..recommendations import similar_books
from ..schemas import (
    BookCreate,
    BookDetail,
    BookSummary,
    BookUpdate,
    CategoryIn,
    CategoryOut,
    CategoryWithCount,
    CopyIn,
    CopyOut,
    CopyUpdate,
    CopyWithBook,
    Message,
    Page,
    ReviewIn,
    ReviewOut,
)
from ..security import DB, CurrentUser, Staff
from ..services import catalog
from ..services.circulation import release_copy
from ..services.common import audit, get_or_404, paginate_args

router = APIRouter(prefix="/api", tags=["catalog"])


# ---------------------------------------------------------------- categories
@router.get("/categories", response_model=list[CategoryWithCount])
def list_categories(db: DB) -> list[CategoryWithCount]:
    rows = db.execute(
        select(Category, func.count(Book.id))
        .outerjoin(Book, Book.category_id == Category.id)
        .group_by(Category.id)
        .order_by(Category.name)
    ).all()
    return [
        CategoryWithCount(**CategoryOut.model_validate(c).model_dump(), book_count=n)
        for c, n in rows
    ]


@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(data: CategoryIn, db: DB, staff: Staff) -> Category:
    if db.scalar(select(Category.id).where(func.lower(Category.name) == data.name.lower())):
        raise Conflict("Category already exists")
    cat = Category(**data.model_dump())
    db.add(cat)
    db.flush()
    audit(db, staff, "category.create", "category", cat.id, cat.name)
    db.commit()
    return cat


@router.put("/categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, data: CategoryIn, db: DB, staff: Staff) -> Category:
    cat = get_or_404(db, Category, category_id, "Category")
    clash = db.scalar(
        select(Category.id).where(
            func.lower(Category.name) == data.name.lower(), Category.id != category_id
        )
    )
    if clash:
        raise Conflict("Category already exists")
    cat.name, cat.description = data.name, data.description
    audit(db, staff, "category.update", "category", cat.id, cat.name)
    db.commit()
    return cat


@router.delete("/categories/{category_id}", response_model=Message)
def delete_category(category_id: int, db: DB, staff: Staff) -> Message:
    cat = get_or_404(db, Category, category_id, "Category")
    if db.scalar(select(func.count(Book.id)).where(Book.category_id == category_id)):
        raise Conflict("Category still has books - move or delete them first")
    db.delete(cat)
    audit(db, staff, "category.delete", "category", category_id, cat.name)
    db.commit()
    return Message(detail="Category deleted")


# ---------------------------------------------------------------- books
@router.get("/books", response_model=Page[BookSummary])
def list_books(
    db: DB,
    q: str = "",
    search: str = "",
    category_id: int | None = None,
    category: str | None = None,
    language: str | None = None,
    available_only: bool = False,
    sort: Annotated[str, Query(pattern="^(title|author|newest|year|popular|rating)$")] = "title",
    page: int = 1,
    size: int = 20,
) -> Page[BookSummary]:
    page, size = paginate_args(page, size)
    items, total = catalog.search_books(
        db,
        q=q or search,
        category_id=category_id,
        category=category,
        language=language,
        available_only=available_only,
        sort=sort,
        page=page,
        size=size,
    )
    return Page(items=items, total=total, page=page, size=size)


@router.get("/books/languages", response_model=list[str])
def list_languages(db: DB) -> list[str]:
    return list(db.scalars(select(Book.language).distinct().order_by(Book.language)))


@router.post("/books", response_model=BookDetail, status_code=201)
def create_book(data: BookCreate, db: DB, staff: Staff) -> BookDetail:
    get_or_404(db, Category, data.category_id, "Category")
    if db.scalar(select(Book.id).where(Book.isbn == data.isbn)):
        raise Conflict(f"A book with ISBN {data.isbn} already exists")
    book = Book(**data.model_dump(exclude={"copies", "price"}))
    if not book.cover_url:
        book.cover_url = f"https://covers.openlibrary.org/b/isbn/{book.isbn}-M.jpg?default=false"
    db.add(book)
    db.flush()
    for _ in range(data.copies):
        db.add(
            BookCopy(
                book_id=book.id,
                barcode=catalog.next_barcode(db, book),
                price=data.price,
                acquired_on=clock.today(),
                status=CopyStatus.AVAILABLE,
                condition="good",
            )
        )
        db.flush()
    audit(db, staff, "book.create", "book", book.id, f"{book.title} ({data.copies} copies)")
    db.commit()
    db.refresh(book)
    return catalog.book_detail(db, book)


@router.get("/books/{book_id}", response_model=BookDetail)
def get_book(book_id: int, db: DB) -> BookDetail:
    return catalog.book_detail(db, get_or_404(db, Book, book_id, "Book"))


@router.put("/books/{book_id}", response_model=BookDetail)
def update_book(book_id: int, data: BookUpdate, db: DB, staff: Staff) -> BookDetail:
    book = get_or_404(db, Book, book_id, "Book")
    changes = data.model_dump(exclude_unset=True)
    if "category_id" in changes:
        get_or_404(db, Category, changes["category_id"], "Category")
    if "isbn" in changes and db.scalar(
        select(Book.id).where(Book.isbn == changes["isbn"], Book.id != book_id)
    ):
        raise Conflict("Another book already uses this ISBN")
    for key, value in changes.items():
        setattr(book, key, value)
    audit(db, staff, "book.update", "book", book.id, ", ".join(changes))
    db.commit()
    db.refresh(book)
    return catalog.book_detail(db, book)


@router.delete("/books/{book_id}", response_model=Message)
def delete_book(book_id: int, db: DB, staff: Staff) -> Message:
    book = get_or_404(db, Book, book_id, "Book")
    has_history = db.scalar(
        select(func.count(Loan.id))
        .join(BookCopy, Loan.copy_id == BookCopy.id)
        .where(BookCopy.book_id == book_id)
    )
    if has_history:
        raise Conflict("This book has circulation history - withdraw its copies instead")
    title = book.title
    db.delete(book)
    audit(db, staff, "book.delete", "book", book_id, title)
    db.commit()
    return Message(detail=f"'{title}' deleted")


@router.get("/books/{book_id}/similar", response_model=list[BookSummary])
def similar(book_id: int, db: DB) -> list[BookSummary]:
    return similar_books(db, get_or_404(db, Book, book_id, "Book"))


# ---------------------------------------------------------------- copies
@router.post("/books/{book_id}/copies", response_model=list[CopyOut], status_code=201)
def add_copies(book_id: int, data: CopyIn, db: DB, staff: Staff) -> list[BookCopy]:
    book = get_or_404(db, Book, book_id, "Book")
    created = []
    for _ in range(data.count):
        copy = BookCopy(
            book_id=book.id,
            barcode=catalog.next_barcode(db, book),
            price=data.price,
            condition=data.condition,
            acquired_on=clock.today(),
            status=CopyStatus.AVAILABLE,
        )
        db.add(copy)
        db.flush()
        # New stock goes straight to anyone waiting in the holds queue.
        release_copy(db, copy, staff)
        created.append(copy)
    audit(db, staff, "copy.add", "book", book.id, f"{data.count} copies")
    db.commit()
    return created


@router.get("/copies/{barcode}", response_model=CopyWithBook)
def find_copy(barcode: str, db: DB, staff: Staff) -> CopyWithBook:
    copy = db.scalar(select(BookCopy).where(BookCopy.barcode == barcode.strip()))
    if copy is None:
        raise NotFound(f"No copy with barcode '{barcode}'")
    summary = catalog.summaries_for(db, [copy.book_id])[copy.book_id]
    return CopyWithBook(**CopyOut.model_validate(copy).model_dump(), book=summary)


@router.patch("/copies/{copy_id}", response_model=CopyOut)
def update_copy(copy_id: int, data: CopyUpdate, db: DB, staff: Staff) -> BookCopy:
    copy = get_or_404(db, BookCopy, copy_id, "Copy")
    changes = data.model_dump(exclude_unset=True)
    new_status = changes.pop("status", None)
    if new_status and new_status != copy.status:
        if copy.status in (CopyStatus.ON_LOAN, CopyStatus.ON_HOLD):
            raise Conflict(f"Copy is {copy.status}; return it or cancel the hold first")
        if new_status == CopyStatus.AVAILABLE:
            db.flush()
            release_copy(db, copy, staff)
        else:
            copy.status = new_status
    for key, value in changes.items():
        setattr(copy, key, value)
    audit(db, staff, "copy.update", "copy", copy.id, f"{copy.barcode}: {new_status or 'details'}")
    db.commit()
    return copy


# ---------------------------------------------------------------- reviews
@router.get("/books/{book_id}/reviews", response_model=list[ReviewOut])
def list_reviews(book_id: int, db: DB) -> list[ReviewOut]:
    reviews = db.scalars(
        select(Review).where(Review.book_id == book_id).order_by(Review.created_at.desc())
    )
    return [catalog.review_out(r) for r in reviews]


@router.post("/books/{book_id}/reviews", response_model=ReviewOut, status_code=201)
def add_review(book_id: int, data: ReviewIn, db: DB, user: CurrentUser) -> ReviewOut:
    get_or_404(db, Book, book_id, "Book")
    borrowed = db.scalar(
        select(func.count(Loan.id))
        .join(BookCopy, Loan.copy_id == BookCopy.id)
        .where(BookCopy.book_id == book_id, Loan.user_id == user.id)
    )
    if not borrowed and not user.is_staff:
        raise LibraryError("You can review a book after you have borrowed it")
    review = db.scalar(select(Review).where(Review.book_id == book_id, Review.user_id == user.id))
    if review is None:
        review = Review(book_id=book_id, user_id=user.id, **data.model_dump())
        db.add(review)
    else:
        review.rating, review.comment = data.rating, data.comment
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("You have already reviewed this book") from None
    db.refresh(review)
    return catalog.review_out(review)


@router.delete("/reviews/{review_id}", response_model=Message)
def delete_review(review_id: int, db: DB, user: CurrentUser) -> Message:
    review = get_or_404(db, Review, review_id, "Review")
    if review.user_id != user.id and not user.is_staff:
        raise Forbidden("You can only delete your own reviews")
    db.delete(review)
    db.commit()
    return Message(detail="Review deleted")
