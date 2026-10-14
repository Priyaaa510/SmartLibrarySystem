from fastapi.testclient import TestClient


def test_dashboard(client: TestClient, staff) -> None:  # type: ignore[no-untyped-def]
    d = client.get("/api/reports/dashboard", headers=staff).json()
    assert d["titles"] == 34
    assert d["active_loans"] == 9 and d["overdue_loans"] == 2
    assert d["holds_waiting"] == 3 and d["holds_ready"] == 1
    assert d["fines_outstanding"] == 35
    assert d["copies_by_status"]["on_loan"] == 9


def test_trend_top_books_categories(client: TestClient, staff) -> None:  # type: ignore[no-untyped-def]
    trend = client.get("/api/reports/circulation", headers=staff, params={"days": 30}).json()
    assert len(trend) == 30 and sum(d["issued"] for d in trend) > 0
    top = client.get("/api/reports/top-books", headers=staff, params={"limit": 5}).json()
    counts = [b["times_borrowed"] for b in top]
    assert counts == sorted(counts, reverse=True)
    cats = client.get("/api/reports/categories", headers=staff).json()
    assert sum(c["titles"] for c in cats) == 34


def test_overdue_and_member_reports(client: TestClient, staff) -> None:  # type: ignore[no-untyped-def]
    overdue = client.get("/api/reports/overdue", headers=staff).json()
    assert {x["member_name"] for x in overdue} == {"Rahul Sharma", "Sneha Patel"}
    members = client.get("/api/reports/members", headers=staff).json()
    assert len(members) == 6
    sneha = next(m for m in members if m["member"] == "Sneha Patel")
    assert sneha["fines_unpaid"] == 35 and sneha["overdue"] == 1


def test_csv_exports(client: TestClient, staff) -> None:  # type: ignore[no-untyped-def]
    for kind in ["books", "loans", "overdue", "fines", "members"]:
        r = client.get(f"/api/reports/export/{kind}.csv", headers=staff)
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
        assert len(r.text.splitlines()) > 1
    assert client.get("/api/reports/export/nope.csv", headers=staff).status_code == 404


def test_activity_log(client: TestClient, staff) -> None:  # type: ignore[no-untyped-def]
    client.post("/api/categories", headers=staff, json={"name": "Poetry"})
    log = client.get("/api/activity", headers=staff).json()
    assert log["items"][0]["action"] == "category.create"
    assert log["items"][0]["actor"] == "Meera Iyer"


def test_recommendation_strategies(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    rahul = login("rahul@example.com")
    names = [s["name"] for s in client.get("/api/recommendations/strategies").json()]
    assert names == ["hybrid", "category", "history", "popular"]
    borrowed = {
        x["book_id"]
        for x in client.get("/api/loans", headers=rahul, params={"size": 100}).json()["items"]
    }
    for strategy in names:
        recs = client.get(
            "/api/recommendations", headers=rahul, params={"strategy": strategy}
        ).json()
        assert recs, strategy
        assert not borrowed & {b["id"] for b in recs}, "never recommend already-borrowed books"
    by_cat = client.get("/api/recommendations", headers=rahul, params={"strategy": "category"})
    assert {b["category"]["name"] for b in by_cat.json()} <= {
        "Programming",
        "Artificial Intelligence",
    }


def test_similar_books(client: TestClient) -> None:
    similar = client.get("/api/books/1/similar").json()
    assert similar and all(b["id"] != 1 for b in similar)


def test_notifications(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    rahul = login("rahul@example.com")
    assert client.get("/api/notifications/unread-count", headers=rahul).json()["unread"] == 1
    note = client.get("/api/notifications", headers=rahul).json()[0]
    client.post(f"/api/notifications/{note['id']}/read", headers=rahul)
    assert client.get("/api/notifications/unread-count", headers=rahul).json()["unread"] == 0
    priya = login("priya@example.com")
    assert client.post(f"/api/notifications/{note['id']}/read", headers=priya).status_code == 404


def test_performance(client: TestClient) -> None:
    perf = client.get("/api/performance").json()
    assert perf["records_scanned"] == 34 * 2000
    assert perf["linear_complexity"] == "O(n)"
