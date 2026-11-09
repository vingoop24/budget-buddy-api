from datetime import date

from app.services import ai

TODAY = date.today()
THIS_MONTH = TODAY.strftime("%Y-%m")


def add(client, **overrides):
    body = {
        "merchant": "Cafe",
        "amount": 10.0,
        "currency": "USD",
        "category": "Food & Dining",
        "date": TODAY.isoformat(),
    } | overrides
    res = client.post("/expenses", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def test_health_works_without_openai_key(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "running", "ai_enabled": False}


def test_expense_crud(client):
    created = add(client, merchant="  Blue Bottle ", amount=4.5)
    assert created["merchant"] == "Blue Bottle"
    assert created["has_receipt"] is False

    res = client.patch(f"/expenses/{created['id']}", json={"amount": 5.25, "notes": "latte"})
    assert res.status_code == 200
    assert res.json()["amount"] == 5.25
    assert res.json()["notes"] == "latte"

    assert client.get(f"/expenses/{created['id']}").json()["amount"] == 5.25
    assert client.delete(f"/expenses/{created['id']}").status_code == 204
    assert client.get(f"/expenses/{created['id']}").status_code == 404
    assert client.delete(f"/expenses/{created['id']}").status_code == 404


def test_validation(client):
    bad = {"merchant": "", "amount": -1, "currency": "dollars", "date": "nope"}
    res = client.post("/expenses", json=bad)
    assert res.status_code == 422
    fields = {err["loc"][-1] for err in res.json()["detail"]}
    assert {"merchant", "amount", "currency", "date"} <= fields

    created = add(client)
    assert client.patch(f"/expenses/{created['id']}", json={"amount": None}).status_code == 422


def test_list_filters_and_order(client):
    add(client, merchant="Old", date="2024-01-15", category="Travel")
    add(client, merchant="Uber", date=TODAY.isoformat(), category="Transport", notes="airport")
    add(client, merchant="Lunch", date=TODAY.isoformat())

    month = client.get("/expenses", params={"month": THIS_MONTH}).json()
    assert [e["merchant"] for e in month] == ["Lunch", "Uber"]  # newest first

    assert len(client.get("/expenses").json()) == 3
    assert [e["merchant"] for e in client.get("/expenses", params={"category": "Travel"}).json()] == ["Old"]
    assert [e["merchant"] for e in client.get("/expenses", params={"q": "AIRPORT"}).json()] == ["Uber"]
    assert client.get("/expenses", params={"month": "2024-13"}).status_code == 422


def test_budget_persists_and_summary_is_monthly(client):
    assert client.get("/budget").json() == {"amount": 1500.0, "currency": "USD"}
    assert client.put("/budget", json={"amount": 200, "currency": "usd"}).json() == {
        "amount": 200.0,
        "currency": "USD",
    }

    add(client, amount=120, category="Groceries")
    add(client, amount=50)
    add(client, amount=999, date="2020-05-01")  # different month: ignored
    add(client, amount=30, currency="EUR")  # different currency: reported separately

    s = client.get("/summary").json()
    assert s["month"] == THIS_MONTH
    assert s["monthly_budget"] == 200
    assert s["total_spent"] == 170
    assert s["remaining"] == 30
    assert s["percent_used"] == 85
    assert s["status"] == "warning"
    assert s["category_totals"] == {"Groceries": 120, "Food & Dining": 50}
    assert s["other_currency_totals"] == {"EUR": 30}
    assert s["expense_count"] == 3
    assert len(s["recent_expenses"]) == 3

    old = client.get("/summary", params={"month": "2020-05"}).json()
    assert old["total_spent"] == 999
    assert old["status"] == "over_budget"

    # legacy alias
    assert client.get("/ai-insights").json()["total_spent"] == 170


def test_categories_include_custom(client):
    add(client, category="Pets")
    cats = client.get("/categories").json()
    assert cats[0] == "Food & Dining"
    assert cats[-1] == "Pets"


def test_receipt_upload_uses_safe_random_names(client, png_bytes):
    exp = add(client)
    res = client.post(
        f"/expenses/{exp['id']}/receipt",
        files={"receipt": ("../../evil.png", png_bytes, "image/png")},
    )
    assert res.status_code == 200
    assert res.json()["has_receipt"] is True

    img = client.get(f"/expenses/{exp['id']}/receipt")
    assert img.status_code == 200
    assert img.content == png_bytes

    not_image = client.post(
        f"/expenses/{exp['id']}/receipt", files={"receipt": ("a.png", b"hello", "image/png")}
    )
    assert not_image.status_code == 400


def test_scan_and_save_with_ai(client, png_bytes, monkeypatch):
    monkeypatch.setattr(ai, "ai_enabled", lambda: True)
    monkeypatch.setattr(
        ai,
        "extract_receipt",
        lambda data, mime: {
            "merchant": "Trader Joe's",
            "amount": "$23,40",
            "currency": "usd",
            "category": "groceries",
            "date": "2026-11-02",
        },
    )
    calls = []
    for _ in range(2):
        res = client.post("/scan-and-save-receipt", files={"receipt": ("receipt.jpg", png_bytes, "image/png")})
        assert res.status_code == 201, res.text
        calls.append(res.json())

    exp = calls[0]["expense"]
    assert calls[0]["source"] == "ai"
    assert exp["merchant"] == "Trader Joe's"
    assert exp["amount"] == 23.40
    assert exp["currency"] == "USD"
    assert exp["category"] == "Groceries"
    assert exp["date"] == "2026-11-02"
    # Same client filename twice must not overwrite the first receipt.
    first = client.get(f"/expenses/{calls[0]['expense']['id']}/receipt")
    second = client.get(f"/expenses/{calls[1]['expense']['id']}/receipt")
    assert first.status_code == second.status_code == 200


def test_scan_falls_back_to_ocr_when_ai_fails(client, png_bytes, monkeypatch):
    def boom(data, mime):
        raise ai.AIUnavailable("bad json")

    monkeypatch.setattr(ai, "extract_receipt", boom)
    monkeypatch.setattr(
        "app.services.receipts._ocr", lambda data: {"merchant": "CORNER SHOP", "amount": 7.5, "date": ""}
    )
    client.put("/budget", json={"amount": 500, "currency": "EUR"})
    res = client.post("/scan-receipt", files={"receipt": ("r.png", png_bytes, "image/png")})
    assert res.status_code == 200
    body = res.json()
    assert body.pop("receipt_token")
    assert body == {
        "merchant": "CORNER SHOP",
        "amount": 7.5,
        "currency": "EUR",
        "category": "Other",
        "date": TODAY.isoformat(),
        "source": "ocr",
        "missing": ["currency", "category", "date"],
    }


def test_scan_review_then_confirm(client, png_bytes, monkeypatch):
    monkeypatch.setattr(
        ai, "extract_receipt", lambda data, mime: {"merchant": "", "amount": "n/a", "date": "2026-11-01"}
    )
    monkeypatch.setattr(ai, "ai_enabled", lambda: True)

    scan = client.post("/scan-receipt", files={"receipt": ("r.png", png_bytes, "image/png")}).json()
    assert scan["source"] == "ai"
    assert set(scan["missing"]) == {"merchant", "amount", "currency", "category"}
    assert scan["merchant"] == "Unknown merchant" and scan["amount"] == 0
    # Reviewing must not create anything.
    assert client.get("/expenses").json() == []

    # The user corrects the fields, then confirms.
    res = client.post(
        "/expenses",
        json={
            "merchant": "Bakery",
            "amount": 6.2,
            "currency": "USD",
            "category": "Food & Dining",
            "date": scan["date"],
            "receipt_token": scan["receipt_token"],
        },
    )
    assert res.status_code == 201, res.text
    exp = res.json()
    assert exp["has_receipt"] is True
    img = client.get(f"/expenses/{exp['id']}/receipt")
    assert img.status_code == 200 and img.content == png_bytes

    # A token can only be used once.
    again = client.post(
        "/expenses",
        json={"merchant": "Dup", "amount": 1, "date": scan["date"], "receipt_token": scan["receipt_token"]},
    )
    assert again.status_code == 400
    assert len(client.get("/expenses").json()) == 1


def test_receipt_token_must_be_well_formed(client):
    res = client.post(
        "/expenses",
        json={"merchant": "X", "amount": 1, "date": TODAY.isoformat(), "receipt_token": "../../etc/passwd"},
    )
    assert res.status_code == 422
    assert client.get("/expenses").json() == []


def test_assistant_without_key_returns_503(client):
    res = client.post("/ai-assistant", json={"question": "How am I doing?"})
    assert res.status_code == 503


def test_assistant_with_key(client, monkeypatch):
    seen = {}

    def fake(question, summary):
        seen.update(summary)
        return "You're on track."

    monkeypatch.setattr(ai, "ask_assistant", fake)
    add(client, amount=12)
    res = client.post("/ai-assistant", json={"question": "How am I doing?"})
    assert res.status_code == 200
    assert res.json() == {"question": "How am I doing?", "response": "You're on track."}
    assert seen["total_spent"] == 12


def test_category_budgets_crud(client):
    assert client.get("/category-budgets").json() == []
    res = client.put("/category-budgets/Groceries", json={"amount": 300})
    assert res.status_code == 200 and res.json() == {"category": "Groceries", "amount": 300.0}
    client.put("/category-budgets/Groceries", json={"amount": 250})  # update, not duplicate
    client.put("/category-budgets/Pets", json={"amount": 40})  # custom category
    assert client.get("/category-budgets").json() == [
        {"category": "Groceries", "amount": 250.0},
        {"category": "Pets", "amount": 40.0},
    ]
    assert client.put("/category-budgets/Groceries", json={"amount": 0}).status_code == 422
    assert client.delete("/category-budgets/Pets").status_code == 204
    assert client.delete("/category-budgets/Pets").status_code == 404
    assert [c["category"] for c in client.get("/category-budgets").json()] == ["Groceries"]


def test_summary_category_limits_and_alerts(client):
    client.put("/budget", json={"amount": 1000, "currency": "USD"})
    client.put("/category-budgets/Groceries", json={"amount": 100})
    client.put("/category-budgets/Transport", json={"amount": 50})
    client.put("/category-budgets/Travel", json={"amount": 500})
    add(client, amount=120, category="Groceries")  # 120% -> over
    add(client, amount=42, category="Transport")  # 84% -> warning
    add(client, amount=10, category="Travel")  # 2% -> good
    add(client, amount=999, category="Groceries", date="2020-01-01")  # other month: ignored

    s = client.get("/summary").json()
    cats = {c["category"]: c for c in s["category_budgets"]}
    assert [c["category"] for c in s["category_budgets"]] == ["Groceries", "Transport", "Travel"]
    assert cats["Groceries"] == {
        "category": "Groceries", "limit": 100.0, "spent": 120.0,
        "remaining": -20.0, "percent_used": 120.0, "status": "over_budget",
    }
    assert cats["Transport"]["status"] == "warning"
    assert cats["Travel"]["status"] == "good"

    assert s["status"] == "good"  # 172 of 1000 overall
    assert [(a["level"], a["category"]) for a in s["alerts"]] == [
        ("over", "Groceries"),
        ("warning", "Transport"),
    ]
    assert "20.00 USD over" in s["alerts"][0]["message"]


def test_overall_budget_alert(client):
    client.put("/budget", json={"amount": 100, "currency": "USD"})
    add(client, amount=85)
    s = client.get("/summary").json()
    assert s["alerts"] == [
        {"level": "warning", "category": None, "message": "You've used 85% of your monthly budget. 15.00 USD left."}
    ]
    add(client, amount=30)
    assert client.get("/summary").json()["alerts"][0]["level"] == "over"


def test_trends(client):
    add(client, amount=10, date="2026-09-03")
    add(client, amount=5.5, date="2026-09-20")
    add(client, amount=20, date="2026-11-01")
    add(client, amount=99, date="2026-11-02", currency="EUR")  # other currency excluded
    add(client, amount=7, date="2026-05-01")  # before the window

    t = client.get("/trends", params={"months": 3, "end": "2026-11"}).json()
    assert t["currency"] == "USD"
    assert t["months"] == [
        {"month": "2026-09", "total_spent": 15.5},
        {"month": "2026-10", "total_spent": 0.0},
        {"month": "2026-11", "total_spent": 20.0},
    ]
    # Year boundary
    t = client.get("/trends", params={"months": 2, "end": "2026-01"}).json()
    assert [m["month"] for m in t["months"]] == ["2025-12", "2026-01"]
    assert client.get("/trends", params={"months": 0}).status_code == 422
