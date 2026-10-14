from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}


def test_register_login_and_profile(client: TestClient) -> None:
    r = client.post(
        "/api/auth/register",
        json={"name": "New Reader", "email": "new@x.com", "password": "secret1"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["member_code"].startswith("LIB")
    assert body["user"]["membership_type"]["name"] == "Student"
    h = {"Authorization": f"Bearer {body['access_token']}"}

    assert client.get("/api/auth/me", headers=h).json()["email"] == "new@x.com"
    r = client.put("/api/auth/me", headers=h, json={"preferred_categories": ["Fiction"]})
    assert r.json()["preferred_categories"] == ["Fiction"]

    dup = client.post(
        "/api/auth/register", json={"name": "Again", "email": "NEW@x.com", "password": "secret1"}
    )
    assert dup.status_code == 409

    r = client.post(
        "/api/auth/change-password",
        headers=h,
        json={"current_password": "secret1", "new_password": "secret2"},
    )
    assert r.status_code == 200
    bad = client.post("/api/auth/login", json={"email": "new@x.com", "password": "secret1"})
    assert bad.status_code == 401
    ok = client.post("/api/auth/login", json={"email": "new@x.com", "password": "secret2"})
    assert ok.status_code == 200


def test_role_based_access(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    assert client.get("/api/members").status_code == 401
    member = login("rahul@example.com")
    assert client.get("/api/members", headers=member).status_code == 403
    assert client.get("/api/reports/dashboard", headers=member).status_code == 403
    r = client.post(
        "/api/books",
        headers=member,
        json={"isbn": "1", "title": "x", "author": "y", "category_id": 1},
    )
    assert r.status_code == 403


def test_only_admin_creates_staff(client: TestClient, staff, admin) -> None:  # type: ignore[no-untyped-def]
    payload = {"name": "Second Librarian", "email": "lib2@x.com", "password": "secret1"}
    r = client.post("/api/members", headers=staff, json={**payload, "role": "librarian"})
    assert r.status_code == 403
    r = client.post("/api/members", headers=admin, json={**payload, "role": "librarian"})
    assert r.status_code == 201 and r.json()["member_code"].startswith("STF")


def test_catalog_search_filter_sort(client: TestClient) -> None:
    r = client.get("/api/books", params={"q": "python"}).json()
    titles = {b["title"] for b in r["items"]}
    assert {"Fluent Python", "Python Crash Course"} <= titles

    r = client.get("/api/books", params={"category": "Fiction", "size": 100}).json()
    assert r["total"] == 6 and all(b["category"]["name"] == "Fiction" for b in r["items"])

    # Refactoring's only copy is on loan, so it is hidden when filtering by availability.
    r = client.get("/api/books", params={"q": "Refactoring", "available_only": True}).json()
    assert r["total"] == 0

    r = client.get("/api/books", params={"sort": "popular", "size": 2}).json()
    assert r["items"][0]["times_borrowed"] >= r["items"][1]["times_borrowed"]
    assert r["page"] == 1 and r["size"] == 2 and r["total"] == 34


def test_book_crud_and_copies(client: TestClient, staff) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "isbn": "9999999999",
        "title": "Test Driven Development",
        "author": "Kent Beck",
        "category_id": 1,
        "copies": 2,
        "price": 400,
    }
    r = client.post("/api/books", headers=staff, json=payload)
    assert r.status_code == 201, r.text
    book = r.json()
    assert book["total_copies"] == 2 and book["available_copies"] == 2
    assert [c["barcode"] for c in book["copies"]] == [
        f"BK{book['id']:05d}-001",
        f"BK{book['id']:05d}-002",
    ]
    assert client.post("/api/books", headers=staff, json=payload).status_code == 409

    r = client.post(f"/api/books/{book['id']}/copies", headers=staff, json={"count": 1})
    assert r.status_code == 201
    r = client.put(f"/api/books/{book['id']}", headers=staff, json={"edition": "1st"})
    assert r.json()["edition"] == "1st" and r.json()["total_copies"] == 3

    copy_id = book["copies"][0]["id"]
    r = client.patch(f"/api/copies/{copy_id}", headers=staff, json={"status": "maintenance"})
    assert r.json()["status"] == "maintenance"
    assert client.get(f"/api/books/{book['id']}").json()["available_copies"] == 2

    assert client.delete(f"/api/books/{book['id']}", headers=staff).status_code == 200
    assert client.get(f"/api/books/{book['id']}").status_code == 404


def test_cannot_delete_book_with_history(client: TestClient, staff) -> None:  # type: ignore[no-untyped-def]
    r = client.delete("/api/books/1", headers=staff)
    assert r.status_code == 409


def test_categories(client: TestClient, staff) -> None:  # type: ignore[no-untyped-def]
    r = client.post("/api/categories", headers=staff, json={"name": "Poetry"})
    assert r.status_code == 201
    assert client.post("/api/categories", headers=staff, json={"name": "poetry"}).status_code == 409
    cats = {c["name"]: c for c in client.get("/api/categories").json()}
    assert cats["Poetry"]["book_count"] == 0 and cats["Fiction"]["book_count"] == 6
    assert (
        client.delete(f"/api/categories/{cats['Fiction']['id']}", headers=staff).status_code == 409
    )
    assert (
        client.delete(f"/api/categories/{cats['Poetry']['id']}", headers=staff).status_code == 200
    )


def test_reviews_require_borrowing(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    rahul = login("rahul@example.com")
    # Rahul has Clean Code (book 1) on loan right now.
    r = client.post("/api/books/1/reviews", headers=rahul, json={"rating": 5, "comment": "Great"})
    assert r.status_code == 201
    r = client.post("/api/books/1/reviews", headers=rahul, json={"rating": 4, "comment": "Edit"})
    assert r.json()["rating"] == 4  # a second review updates the first
    reviews = client.get("/api/books/1/reviews").json()
    assert any(rv["reviewer"] == "Rahul Sharma" and rv["rating"] == 4 for rv in reviews)

    r = client.post(
        "/api/auth/register", json={"name": "Newbie", "email": "nb@x.com", "password": "secret1"}
    )
    newbie = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.post("/api/books/1/reviews", headers=newbie, json={"rating": 3})
    assert r.status_code == 400
