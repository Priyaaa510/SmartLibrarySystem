from typing import Any

from fastapi.testclient import TestClient


def book_id(client: TestClient, title: str) -> int:
    items = client.get("/api/books", params={"q": title}).json()["items"]
    return next(b["id"] for b in items if b["title"] == title)


def new_member(client: TestClient, staff: dict[str, str], email: str, plan: int = 1) -> int:
    r = client.post(
        "/api/members",
        headers=staff,
        json={"name": "Member " + email.split("@")[0], "email": email, "password": "member123",
              "membership_type_id": plan},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


def checkout(client: TestClient, staff: dict[str, str], member: Any, **kw: Any) -> Any:
    return client.post("/api/loans/checkout", headers=staff, json={"member": str(member), **kw})


def test_issue_and_return_updates_availability(client: TestClient, staff) -> None:  # type: ignore[no-untyped-def]
    mid = new_member(client, staff, "a@x.com")
    bid = book_id(client, "The Alchemist")
    before = client.get(f"/api/books/{bid}").json()["available_copies"]

    r = checkout(client, staff, mid, book_id=bid)
    assert r.status_code == 201, r.text
    loan = r.json()
    assert loan["book_title"] == "The Alchemist" and loan["renew_count"] == 0
    assert client.get(f"/api/books/{bid}").json()["available_copies"] == before - 1

    # same title twice is refused
    assert checkout(client, staff, mid, book_id=bid).status_code == 409

    r = client.post("/api/loans/checkin", headers=staff, json={"barcode": loan["barcode"]})
    assert r.status_code == 200
    assert r.json()["loan"]["status"] == "returned" and r.json()["fines"] == []
    assert client.get(f"/api/books/{bid}").json()["available_copies"] == before


def test_checkout_by_member_code_and_barcode(client: TestClient, staff) -> None:  # type: ignore[no-untyped-def]
    mid = new_member(client, staff, "code@x.com")
    code = f"LIB{mid:06d}"
    r = checkout(client, staff, code.lower(), barcode="BK00018-002")
    assert r.status_code == 201, r.text
    assert r.json()["member_code"] == code
    r = checkout(client, staff, mid, barcode="BK00018-002")
    assert r.status_code == 409  # already on loan


def test_borrowing_limit(client: TestClient, staff) -> None:  # type: ignore[no-untyped-def]
    mid = new_member(client, staff, "limit@x.com")  # Student plan: 3 books
    for title in ["The Alchemist", "Wings of Fire", "Python Crash Course"]:
        assert checkout(client, staff, mid, book_id=book_id(client, title)).status_code == 201
    r = checkout(client, staff, mid, book_id=book_id(client, "1984"))
    assert r.status_code == 400 and "limit" in r.json()["detail"]


def test_blocked_members(client: TestClient, staff) -> None:  # type: ignore[no-untyped-def]
    alchemist = book_id(client, "The Alchemist")
    # Rahul has an overdue loan, Vikram's membership has expired.
    for email, reason in [("rahul", "overdue"), ("vikram", "expired")]:
        mid = client.get("/api/members", headers=staff, params={"q": email}).json()["items"][0]
        r = checkout(client, staff, mid["id"], book_id=alchemist)
        assert r.status_code == 400 and reason in r.json()["detail"], r.text

    vikram = client.get("/api/members", headers=staff, params={"q": "vikram"}).json()["items"][0]
    r = client.post(f"/api/members/{vikram['id']}/renew-membership", headers=staff)
    assert r.status_code == 200
    assert checkout(client, staff, vikram["id"], book_id=alchemist).status_code == 201


def test_overdue_return_creates_fine_and_payment(client: TestClient, staff, login, travel) -> None:  # type: ignore[no-untyped-def]
    mid = new_member(client, staff, "late@x.com")  # Student: 14 days, ₹5/day
    loan = checkout(client, staff, mid, book_id=book_id(client, "The Hobbit")).json()

    travel(17)  # 3 days late
    loans = client.get("/api/loans", headers=staff, params={"status": "overdue"}).json()
    mine = next(x for x in loans["items"] if x["id"] == loan["id"])
    assert mine["overdue_days"] == 3 and mine["accrued_fine"] == 15

    r = client.post(f"/api/loans/{loan['id']}/return", headers=staff)
    assert r.status_code == 200, r.text
    fines = r.json()["fines"]
    assert len(fines) == 1 and fines[0]["amount"] == 15 and fines[0]["reason"] == "overdue"

    member = login("late@x.com")
    summary = client.get("/api/me/summary", headers=member).json()
    assert summary["eligibility"]["unpaid_fines"] == 15
    assert client.post(f"/api/fines/{fines[0]['id']}/waive", headers=member).status_code == 403
    r = client.post(f"/api/fines/{fines[0]['id']}/pay", headers=member)
    assert r.json()["status"] == "paid"
    assert client.post(f"/api/fines/{fines[0]['id']}/pay", headers=member).status_code == 409


def test_unpaid_fines_block_borrowing(client: TestClient, staff) -> None:  # type: ignore[no-untyped-def]
    mid = new_member(client, staff, "debt@x.com")
    r = client.post("/api/fines", headers=staff, json={"member_id": mid, "amount": 250})
    assert r.status_code == 201
    r = checkout(client, staff, mid, book_id=book_id(client, "The Alchemist"))
    assert r.status_code == 400 and "Unpaid fines" in r.json()["detail"]
    fine = client.get("/api/fines", headers=staff, params={"member_id": mid}).json()["items"][0]
    r = client.post(f"/api/fines/{fine['id']}/waive", headers=staff, json={"note": "goodwill"})
    assert r.json()["status"] == "waived"
    assert checkout(client, staff, mid, book_id=book_id(client, "The Alchemist")).status_code == 201


def test_renewal_rules(client: TestClient, staff, login, travel) -> None:  # type: ignore[no-untyped-def]
    mid = new_member(client, staff, "renew@x.com")  # Student: 2 renewals
    loan = checkout(client, staff, mid, book_id=book_id(client, "The Alchemist")).json()
    member = login("renew@x.com")
    other = login("arjun@example.com")
    assert client.post(f"/api/loans/{loan['id']}/renew", headers=other).status_code == 403

    r1 = client.post(f"/api/loans/{loan['id']}/renew", headers=member)
    assert r1.status_code == 200 and r1.json()["renew_count"] == 1
    assert r1.json()["due_date"] > loan["due_date"]
    assert client.post(f"/api/loans/{loan['id']}/renew", headers=member).status_code == 200
    r3 = client.post(f"/api/loans/{loan['id']}/renew", headers=member)
    assert r3.status_code == 400 and "limit" in r3.json()["detail"]

    loan2 = checkout(client, staff, mid, book_id=book_id(client, "Wings of Fire")).json()
    travel(30)
    r = client.post(f"/api/loans/{loan2['id']}/renew", headers=member)
    assert r.status_code == 400 and "Overdue" in r.json()["detail"]


def test_holds_queue_full_lifecycle(client: TestClient, staff, login) -> None:  # type: ignore[no-untyped-def]
    refactoring = book_id(
        client, "Refactoring"
    )  # 1 copy, on loan to Arjun, Rahul then Priya waiting
    rahul, priya = login("rahul@example.com"), login("priya@example.com")
    holds = client.get("/api/reservations", headers=staff, params={"book_id": refactoring}).json()
    assert [h["member_name"] for h in holds["items"]] == ["Rahul Sharma", "Priya Nair"]
    assert [h["queue_position"] for h in holds["items"]] == [1, 2]

    # Arjun cannot renew because people are waiting
    arjun = login("arjun@example.com")
    arjun_loans = client.get("/api/loans", headers=arjun, params={"status": "active"}).json()
    loan = next(x for x in arjun_loans["items"] if x["book_id"] == refactoring)
    assert client.post(f"/api/loans/{loan['id']}/renew", headers=arjun).status_code == 409

    # Return -> copy goes to the hold shelf for Rahul (first in queue)
    r = client.post(f"/api/loans/{loan['id']}/return", headers=staff).json()
    assert r["hold_assigned_to"] == "Rahul Sharma"
    book = client.get(f"/api/books/{refactoring}").json()
    assert book["copies"][0]["status"] == "on_hold" and book["available_copies"] == 0
    notes = client.get("/api/notifications", headers=rahul).json()
    assert notes[0]["kind"] == "hold_ready"

    # Priya cannot take Rahul's held copy
    priya_id = client.get("/api/auth/me", headers=priya).json()["id"]
    r = checkout(client, staff, priya_id, barcode=loan["barcode"])
    assert r.status_code == 409 and "hold shelf" in r.json()["detail"]

    # Rahul cancels -> it moves on to Priya, who collects it
    mine = client.get("/api/reservations", headers=rahul, params={"status": "open"}).json()
    res = next(h for h in mine["items"] if h["book_id"] == refactoring)
    assert res["status"] == "ready"
    assert client.post(f"/api/reservations/{res['id']}/cancel", headers=rahul).status_code == 200
    priya_holds = client.get("/api/reservations", headers=priya, params={"status": "open"}).json()
    assert any(h["book_id"] == refactoring and h["status"] == "ready" for h in priya_holds["items"])
    r = checkout(client, staff, priya_id, book_id=refactoring)
    assert r.status_code == 201, r.text
    after = client.get("/api/reservations", headers=priya, params={"book_id": refactoring}).json()
    assert after["items"][0]["status"] == "fulfilled"


def test_place_hold_rules(client: TestClient, staff, login) -> None:  # type: ignore[no-untyped-def]
    member = login("sneha@example.com")
    alchemist = book_id(client, "The Alchemist")
    r = client.post("/api/reservations", headers=member, json={"book_id": alchemist})
    assert r.status_code == 409 and "on the shelf" in r.json()["detail"]

    sicp = book_id(client, "Structure and Interpretation of Computer Programs")  # 1 copy
    priya_id = client.get("/api/auth/me", headers=login("priya@example.com")).json()["id"]
    assert checkout(client, staff, priya_id, book_id=sicp).status_code == 201
    r = client.post("/api/reservations", headers=member, json={"book_id": sicp})
    assert r.status_code == 201 and r.json()["queue_position"] == 1
    again = client.post("/api/reservations", headers=member, json={"book_id": sicp})
    assert again.status_code == 409
    mine = client.post(
        "/api/reservations", headers=login("priya@example.com"), json={"book_id": sicp}
    )
    assert mine.status_code == 409  # already has it on loan


def test_uncollected_hold_expires(client: TestClient, staff, login, travel) -> None:  # type: ignore[no-untyped-def]
    sapiens = book_id(client, "Sapiens: A Brief History of Humankind")
    travel(5)  # Ananya's pickup window (2 days) has passed
    r = client.post("/api/admin/run-daily-jobs", headers=staff)
    assert r.status_code == 200 and r.json()["expired_holds"] == 1
    assert r.json()["overdue_notices"] >= 2
    book = client.get(f"/api/books/{sapiens}").json()
    assert book["available_copies"] == 3
    again = client.post("/api/admin/run-daily-jobs", headers=staff).json()
    assert again["overdue_notices"] == 0  # reminders are de-duplicated per day


def test_lost_book(client: TestClient, staff) -> None:  # type: ignore[no-untyped-def]
    mid = new_member(client, staff, "lost@x.com")
    loan = checkout(client, staff, mid, book_id=book_id(client, "Cosmos")).json()
    r = client.post(f"/api/loans/{loan['id']}/lost", headers=staff)
    assert r.status_code == 200
    body = r.json()
    assert body["loan"]["status"] == "lost"
    assert body["fines"][0]["reason"] == "lost" and body["fines"][0]["amount"] > 50
    book = client.get(f"/api/books/{loan['book_id']}").json()
    assert book["total_copies"] == 0 and book["copies"][0]["status"] == "lost"


def test_damaged_return(client: TestClient, staff) -> None:  # type: ignore[no-untyped-def]
    mid = new_member(client, staff, "dmg@x.com")
    loan = checkout(client, staff, mid, book_id=book_id(client, "The Alchemist")).json()
    r = client.post(
        f"/api/loans/{loan['id']}/return",
        headers=staff,
        json={"damaged": True, "damage_fee": 120, "notes": "Torn pages"},
    )
    assert r.json()["fines"][0]["reason"] == "damaged" and r.json()["fines"][0]["amount"] == 120
    copy = client.get(f"/api/copies/{loan['barcode']}", headers=staff).json()
    assert copy["status"] == "damaged"
    r = client.patch(f"/api/copies/{copy['id']}", headers=staff, json={"status": "available"})
    assert r.json()["status"] == "available"


def test_member_management(client: TestClient, staff) -> None:  # type: ignore[no-untyped-def]
    mid = new_member(client, staff, "mgmt@x.com")
    r = client.put(f"/api/members/{mid}", headers=staff, json={"membership_type_id": 2})
    assert r.json()["membership_type"]["name"] == "Faculty"
    detail = client.get(f"/api/members/{mid}", headers=staff).json()
    assert detail["eligibility"]["max_books"] == 10

    loan = checkout(client, staff, mid, book_id=book_id(client, "The Alchemist")).json()
    assert client.delete(f"/api/members/{mid}", headers=staff).status_code == 409
    client.post(f"/api/loans/{loan['id']}/return", headers=staff)
    assert client.delete(f"/api/members/{mid}", headers=staff).status_code == 200
    r = client.post("/api/auth/login", json={"email": "mgmt@x.com", "password": "member123"})
    assert r.status_code == 403

    listing = client.get("/api/members", headers=staff, params={"status": "overdue"}).json()
    assert {m["name"] for m in listing["items"]} == {"Rahul Sharma", "Sneha Patel"}
