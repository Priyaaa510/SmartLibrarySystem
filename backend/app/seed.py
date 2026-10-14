"""Demo data. Run `python -m app.seed --reset` to wipe and re-create the database."""

import argparse
import random
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import clock
from .database import Base, SessionLocal, engine
from .models import (
    Book,
    BookCopy,
    Category,
    CopyStatus,
    Fine,
    FineReason,
    FineStatus,
    Loan,
    LoanStatus,
    MembershipType,
    Notification,
    Reservation,
    ReservationStatus,
    Review,
    Role,
    User,
)
from .services.members import create_user

PLANS = [
    ("Student", "Undergraduate & postgraduate students", 3, 14, 2, "5", "200", 12),
    ("Faculty", "Teaching & research staff", 10, 30, 3, "2", "500", 36),
    ("Public", "Community members with a paid membership", 4, 21, 1, "10", "300", 12),
]

CATEGORIES = [
    ("Programming", "Software development & languages"),
    ("Computer Science", "Algorithms, systems, databases & networks"),
    ("Artificial Intelligence", "AI, machine learning & data science"),
    ("Fiction", "Novels & literature"),
    ("Science", "Physics, biology & popular science"),
    ("History", "World & Indian history"),
    ("Self-Help", "Personal development & psychology"),
    ("Business", "Entrepreneurship & management"),
]

# isbn, title, author, publisher, year, category, copies, pages, shelf
BOOKS = [
    ("9780132350884", "Clean Code", "Robert C. Martin", "Prentice Hall", 2008, "Programming", 3, 464),
    ("9780135957059", "The Pragmatic Programmer", "David Thomas, Andrew Hunt", "Addison-Wesley", 2019, "Programming", 2, 352),
    ("9781492056355", "Fluent Python", "Luciano Ramalho", "O'Reilly Media", 2022, "Programming", 2, 1012),
    ("9781593279288", "Python Crash Course", "Eric Matthes", "No Starch Press", 2019, "Programming", 4, 544),
    ("9780134757599", "Refactoring", "Martin Fowler", "Addison-Wesley", 2018, "Programming", 1, 448),
    ("9780201633610", "Design Patterns", "Erich Gamma et al.", "Addison-Wesley", 1994, "Programming", 2, 395),
    ("9780735619678", "Code Complete", "Steve McConnell", "Microsoft Press", 2004, "Programming", 1, 960),
    ("9780262033848", "Introduction to Algorithms", "Thomas H. Cormen et al.", "MIT Press", 2009, "Computer Science", 3, 1312),
    ("9780262510875", "Structure and Interpretation of Computer Programs", "Harold Abelson, Gerald Jay Sussman", "MIT Press", 1996, "Computer Science", 1, 657),
    ("9781449373320", "Designing Data-Intensive Applications", "Martin Kleppmann", "O'Reilly Media", 2017, "Computer Science", 2, 616),
    ("9780078022159", "Database System Concepts", "Abraham Silberschatz et al.", "McGraw-Hill", 2019, "Computer Science", 3, 1376),
    ("9780133594140", "Computer Networking: A Top-Down Approach", "James Kurose, Keith Ross", "Pearson", 2016, "Computer Science", 2, 864),
    ("9780136042594", "Artificial Intelligence: A Modern Approach", "Stuart Russell, Peter Norvig", "Pearson", 2009, "Artificial Intelligence", 3, 1152),
    ("9780262035613", "Deep Learning", "Ian Goodfellow et al.", "MIT Press", 2016, "Artificial Intelligence", 1, 800),
    ("9781492032649", "Hands-On Machine Learning", "Aurélien Géron", "O'Reilly Media", 2019, "Artificial Intelligence", 2, 856),
    ("9780387310732", "Pattern Recognition and Machine Learning", "Christopher M. Bishop", "Springer", 2006, "Artificial Intelligence", 1, 738),
    ("9781101946596", "Life 3.0", "Max Tegmark", "Knopf", 2017, "Artificial Intelligence", 2, 384),
    ("9780062315007", "The Alchemist", "Paulo Coelho", "HarperOne", 2014, "Fiction", 5, 208),
    ("9780061120084", "To Kill a Mockingbird", "Harper Lee", "Harper Perennial", 2006, "Fiction", 3, 336),
    ("9780451524935", "1984", "George Orwell", "Signet Classics", 1961, "Fiction", 3, 328),
    ("9780141439518", "Pride and Prejudice", "Jane Austen", "Penguin Classics", 2002, "Fiction", 2, 480),
    ("9780743273565", "The Great Gatsby", "F. Scott Fitzgerald", "Scribner", 2004, "Fiction", 2, 180),
    ("9780547928227", "The Hobbit", "J.R.R. Tolkien", "Mariner Books", 2012, "Fiction", 2, 300),
    ("9780553380163", "A Brief History of Time", "Stephen Hawking", "Bantam", 1998, "Science", 2, 212),
    ("9780345539434", "Cosmos", "Carl Sagan", "Ballantine Books", 2013, "Science", 1, 432),
    ("9780198788607", "The Selfish Gene", "Richard Dawkins", "Oxford University Press", 2016, "Science", 1, 544),
    ("9780062316097", "Sapiens: A Brief History of Humankind", "Yuval Noah Harari", "Harper", 2015, "History", 3, 464),
    ("9780143031031", "The Discovery of India", "Jawaharlal Nehru", "Penguin India", 2004, "History", 2, 656),
    ("9780060958589", "India After Gandhi", "Ramachandra Guha", "Harper Perennial", 2008, "History", 1, 900),
    ("9788173711466", "Wings of Fire", "A.P.J. Abdul Kalam", "Universities Press", 1999, "Self-Help", 4, 196),
    ("9780735211292", "Atomic Habits", "James Clear", "Avery", 2018, "Self-Help", 3, 320),
    ("9780374533557", "Thinking, Fast and Slow", "Daniel Kahneman", "Farrar, Straus and Giroux", 2013, "Self-Help", 2, 512),
    ("9780307887894", "The Lean Startup", "Eric Ries", "Crown Business", 2011, "Business", 2, 336),
    ("9780804139298", "Zero to One", "Peter Thiel, Blake Masters", "Crown Business", 2014, "Business", 1, 224),
]  # fmt: skip

DESCRIPTIONS = {
    "Programming": "A widely recommended text for developers who want to write better software.",
    "Computer Science": "A foundational computer science reference used in university courses.",
    "Artificial Intelligence": "Covers key ideas and techniques in artificial intelligence.",
    "Fiction": "A celebrated work of fiction loved by generations of readers.",
    "Science": "An accessible exploration of big scientific ideas.",
    "History": "A sweeping account of history and the forces that shaped it.",
    "Self-Help": "Practical insight for personal growth and better thinking.",
    "Business": "Lessons on building companies and creating value.",
}

STAFF = [
    ("Library Admin", "admin@library.com", "admin123", Role.ADMIN),
    ("Meera Iyer", "librarian@library.com", "librarian123", Role.LIBRARIAN),
]

MEMBERS = [
    ("Rahul Sharma", "rahul@example.com", "Student", ["Programming", "Artificial Intelligence"]),
    ("Priya Nair", "priya@example.com", "Faculty", ["Computer Science", "Science"]),
    ("Arjun Reddy", "arjun@example.com", "Student", ["Fiction", "History"]),
    ("Sneha Patel", "sneha@example.com", "Student", ["Self-Help", "Business"]),
    ("Vikram Singh", "vikram@example.com", "Public", ["History", "Science"]),
    ("Ananya Rao", "ananya@example.com", "Student", ["Artificial Intelligence", "Fiction"]),
]

COMMENTS = [
    "Excellent read, highly recommended.",
    "Clear explanations and great examples.",
    "A bit dense in places but worth it.",
    "One of my favourites - borrowed it twice!",
    "Good book, though the middle chapters drag.",
]


def _at(day_offset: int) -> datetime:
    d = clock.today() + timedelta(days=day_offset)
    return datetime.combine(d, time(10, 30), tzinfo=timezone.utc)


def seed(db: Session) -> bool:
    """Populate an empty database with demo data. Returns False if data already exists."""
    if db.scalar(select(func.count(User.id))):
        return False
    rng = random.Random(42)
    today = clock.today()

    plans = {}
    for name, desc, max_books, days, renewals, fine, limit, months in PLANS:
        plan = MembershipType(
            name=name, description=desc, max_books=max_books, loan_days=days, max_renewals=renewals,
            fine_per_day=Decimal(fine), max_unpaid_fine=Decimal(limit), validity_months=months,
        )  # fmt: skip
        db.add(plan)
        plans[name] = plan
    cats = {}
    for name, desc in CATEGORIES:
        cats[name] = Category(name=name, description=desc)
        db.add(cats[name])
    db.flush()

    for name, email, password, role in STAFF:
        create_user(db, name=name, email=email, password=password, role=role)
    members = [
        create_user(
            db, name=name, email=email, password="member123", phone=f"+91 98{i:03d} 4{i:04d}",
            address=f"{10 + i} MG Road, Vijayawada", preferred_categories=prefs,
            membership_type_id=plans[plan].id,
        )
        for i, (name, email, plan, prefs) in enumerate(MEMBERS, start=1)
    ]  # fmt: skip
    # One lapsed membership to demonstrate renewal.
    members[4].membership_expiry = today - timedelta(days=10)

    copies: dict[str, list[BookCopy]] = {}
    books: dict[str, Book] = {}
    for n, (isbn, title, author, publisher, year, cat, count, pages) in enumerate(BOOKS):
        book = Book(
            isbn=isbn, title=title, author=author, publisher=publisher, published_year=year,
            edition=None, language="English", pages=pages, description=DESCRIPTIONS[cat],
            cover_url=f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg?default=false",
            shelf_location=f"{cat[:2].upper()}-{(n % 6) + 1:02d}", category=cats[cat],
        )  # fmt: skip
        db.add(book)
        db.flush()
        books[isbn] = book
        price = Decimal(rng.choice([350, 450, 599, 799, 999]))
        copies[isbn] = []
        for c in range(count):
            copy = BookCopy(
                book_id=book.id, barcode=f"BK{book.id:05d}-{c + 1:03d}",
                status=CopyStatus.AVAILABLE, condition="good",
                acquired_on=today - timedelta(days=rng.randint(200, 1500)), price=price,
            )  # fmt: skip
            db.add(copy)
            copies[isbn].append(copy)
    db.flush()

    librarian = db.scalar(select(User).where(User.role == Role.LIBRARIAN))
    assert librarian is not None

    # ---- returned loan history over the last ~90 days
    isbns = list(books)
    for _ in range(70):
        member = rng.choice(members)
        isbn = rng.choice(isbns)
        copy = rng.choice(copies[isbn])
        assert member.membership_type is not None
        start = -rng.randint(16, 95)
        due = today + timedelta(days=start + member.membership_type.loan_days)
        kept = rng.randint(3, member.membership_type.loan_days + 6)
        returned = _at(start + kept)
        if returned.date() >= today:
            continue
        loan = Loan(
            copy_id=copy.id, user_id=member.id, issued_by_id=librarian.id, issued_at=_at(start),
            due_date=due, returned_at=returned, status=LoanStatus.RETURNED,
        )  # fmt: skip
        db.add(loan)
        db.flush()
        late = (returned.date() - due).days
        if late > 0:
            db.add(
                Fine(
                    user_id=member.id, loan_id=loan.id,
                    amount=late * member.membership_type.fine_per_day,
                    reason=FineReason.OVERDUE, status=FineStatus.PAID,
                    note=f"Returned {late} day(s) late", settled_at=returned,
                    settled_by_id=librarian.id,
                )  # fmt: skip
            )

    # ---- current loans: (member index, isbn, issued days ago)
    current = [
        (0, "9780132350884", 5),  # Rahul - Clean Code
        (0, "9780136042594", 18),  # Rahul - AIMA (overdue for a student: 14-day loans)
        (1, "9781449373320", 10),  # Priya - DDIA
        (1, "9780262033848", 3),  # Priya - CLRS
        (2, "9780451524935", 13),  # Arjun - 1984 (due tomorrow)
        (3, "9780735211292", 20),  # Sneha - Atomic Habits (overdue)
        (5, "9781492032649", 7),  # Ananya - Hands-On ML
        (2, "9780134757599", 2),  # Arjun - Refactoring (only copy -> creates a hold queue)
        (3, "9780262035613", 4),  # Sneha - Deep Learning (only copy)
    ]
    for idx, isbn, ago in current:
        member = members[idx]
        assert member.membership_type is not None
        copy = next(c for c in copies[isbn] if c.status == CopyStatus.AVAILABLE)
        copy.status = CopyStatus.ON_LOAN
        db.add(
            Loan(
                copy_id=copy.id, user_id=member.id, issued_by_id=librarian.id,
                issued_at=_at(-ago), due_date=today + timedelta(days=member.membership_type.loan_days - ago),
                status=LoanStatus.ACTIVE,
            )  # fmt: skip
        )

    # ---- holds queue: two members waiting for Refactoring, one for Deep Learning
    for offset, (idx, isbn) in enumerate(
        [(0, "9780134757599"), (1, "9780134757599"), (5, "9780262035613")]
    ):
        db.add(
            Reservation(
                book_id=books[isbn].id, user_id=members[idx].id, status=ReservationStatus.WAITING,
                created_at=_at(-3 + offset),
            )  # fmt: skip
        )
    # ---- a copy waiting on the hold shelf for Ananya
    shelf_copy = copies["9780062316097"][0]
    shelf_copy.status = CopyStatus.ON_HOLD
    db.add(
        Reservation(
            book_id=books["9780062316097"].id, user_id=members[5].id, copy_id=shelf_copy.id,
            status=ReservationStatus.READY, created_at=_at(-4), ready_at=_at(-1),
            expires_on=today + timedelta(days=2),
        )  # fmt: skip
    )

    # ---- an unpaid fine and a damaged copy
    db.add(
        Fine(
            user_id=members[3].id, amount=Decimal("35"), reason=FineReason.OVERDUE,
            status=FineStatus.UNPAID, note="Returned 7 day(s) late",
        )  # fmt: skip
    )
    copies["9780547928227"][1].status = CopyStatus.DAMAGED
    copies["9780547928227"][1].condition = "damaged"
    copies["9780547928227"][1].notes = "Water damage - sent for rebinding"

    # ---- reviews from members who borrowed the books
    db.flush()
    reviewed: set[tuple[int, int]] = set()
    for loan in db.scalars(select(Loan).where(Loan.status == LoanStatus.RETURNED)).all():
        key = (loan.copy.book_id, loan.user_id)
        if key in reviewed or rng.random() < 0.45:
            continue
        reviewed.add(key)
        db.add(
            Review(
                book_id=key[0], user_id=key[1], rating=rng.choice([3, 4, 4, 5, 5]),
                comment=rng.choice(COMMENTS),
            )  # fmt: skip
        )

    for member in members:
        db.add(
            Notification(
                user_id=member.id, kind="welcome", title="Welcome to Smart Library",
                message="Your membership is active. Browse the catalog and place holds online.",
            )  # fmt: skip
        )
    db.commit()
    return True


def reset_database() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="drop all tables first")
    args = parser.parse_args()
    if args.reset:
        reset_database()
    else:
        Base.metadata.create_all(engine)
    with SessionLocal() as db:
        print("Seeded demo data." if seed(db) else "Database already has data - skipped.")


if __name__ == "__main__":
    main()
