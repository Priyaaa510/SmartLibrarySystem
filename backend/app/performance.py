"""Demonstrates why the catalog is indexed: linear scan vs hash lookup vs a B-tree index."""

from time import perf_counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Book


def compare(db: Session, multiplier: int = 2000) -> dict[str, Any]:
    isbns = list(db.scalars(select(Book.isbn)))
    if not isbns:
        return {"detail": "No books in the catalog"}
    # Unique synthetic keys; the target is the last one, i.e. the linear-scan worst case.
    data = [f"{isbn}-{n}" for n in range(multiplier) for isbn in isbns]
    target = data[-1]

    start = perf_counter()
    next((i for i in data if i == target), None)
    linear = perf_counter() - start

    index = {key: n for n, key in enumerate(data)}
    start = perf_counter()
    index.get(target)
    dictionary = perf_counter() - start

    start = perf_counter()
    db.scalar(select(Book.id).where(Book.isbn == isbns[-1]))
    database = perf_counter() - start

    return {
        "records_scanned": len(data),
        "target_key": target,
        "linear_seconds": linear,
        "dictionary_seconds": dictionary,
        "postgres_indexed_seconds": database,
        "linear_complexity": "O(n)",
        "dictionary_complexity": "O(1) average",
        "postgres_complexity": "O(log n) B-tree unique index on books.isbn (incl. round-trip)",
    }
