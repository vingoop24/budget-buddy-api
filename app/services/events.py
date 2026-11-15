"""Product analytics: record events and turn them into the PRD's weekly KPIs.

Events
- expense_created  {source: "manual" | "scan", category, currency}
- scan_completed   {source: "ai" | "ocr", missing: [fields], duration_ms, model}
- scan_confirmed   {corrected: [fields], fields: {field: "correct" | "corrected" | "unread"}}

A scanned field counts as correct only if the scan read it AND the user saved it
unchanged; an unread field (one the scan left blank) is never counted as correct.
"""

from datetime import date, datetime, timedelta, timezone

from sqlmodel import Session, select

from app.config import settings
from app.models import Event

SCAN_FIELDS = ("merchant", "amount", "date", "category")  # the PRD's success-rate fields


def record(session: Session, name: str, expense_id: int | None = None, **properties) -> None:
    """Add an event to the session; the caller's commit saves it with the change it describes."""
    session.add(Event(name=name, expense_id=expense_id, properties=properties))


def compare_scan(extracted: dict, saved: dict) -> dict:
    """Field-by-field outcome of a confirmed scan: correct, corrected or unread."""
    missing = set(extracted.get("missing", []))
    fields = {}
    for field in SCAN_FIELDS + ("currency",):
        if field in missing:
            fields[field] = "unread"
            continue
        before, after = extracted.get(field), saved.get(field)
        if field == "amount":
            same = before is not None and after is not None and abs(float(before) - float(after)) < 0.005
        elif field == "merchant":
            same = str(before or "").strip().casefold() == str(after or "").strip().casefold()
        else:
            same = str(before) == str(after)
        fields[field] = "correct" if same else "corrected"
    return {
        "fields": fields,
        "corrected": [f for f, outcome in fields.items() if outcome != "correct"],
    }


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())  # Monday


def build_metrics(session: Session, weeks: int) -> dict:
    """The PRD's KPIs per calendar week (Monday start), oldest first, ending this week."""
    this_week = _week_start(datetime.now(timezone.utc).date())
    first = this_week - timedelta(weeks=weeks - 1)
    since = datetime.combine(first, datetime.min.time(), tzinfo=timezone.utc)
    events = session.exec(select(Event).where(Event.created_at >= since)).all()

    buckets = {first + timedelta(weeks=i): [] for i in range(weeks)}
    for e in events:
        created = e.created_at if e.created_at.tzinfo else e.created_at.replace(tzinfo=timezone.utc)
        key = _week_start(created.date())
        if key in buckets:
            buckets[key].append(e)

    def rate(part: int, whole: int) -> float | None:
        return round(part / whole, 3) if whole else None

    rows = []
    field_totals = {f: [0, 0] for f in SCAN_FIELDS + ("currency",)}  # [correct, confirmed]
    for start, items in buckets.items():
        created = [e for e in items if e.name == "expense_created"]
        scanned = [e for e in created if e.properties.get("source") == "scan"]
        confirmed = [e for e in items if e.name == "scan_confirmed"]
        clean = [e for e in confirmed if not set(e.properties.get("corrected", [])) & set(SCAN_FIELDS)]
        for e in confirmed:
            for field, outcome in e.properties.get("fields", {}).items():
                if field in field_totals:
                    field_totals[field][1] += 1
                    field_totals[field][0] += outcome == "correct"
        # Single-user until accounts land (Phase 3): "active users" is 1 if anything was logged.
        active_users = 1 if created else 0
        rows.append(
            {
                "week_start": start.isoformat(),
                "expenses_logged": len(created),
                "expenses_per_active_user": len(created) if active_users else 0,
                "scan_share": rate(len(scanned), len(created)),
                "scans_completed": sum(e.name == "scan_completed" for e in items),
                "scans_confirmed": len(confirmed),
                "scan_success_rate": rate(len(clean), len(confirmed)),
                "active_users": active_users,
            }
        )

    return {
        "weeks": rows,
        "field_accuracy": {f: rate(c, n) for f, (c, n) in field_totals.items()},
        "model": settings.openai_model,
        "note": "Single-user until accounts are added (Phase 3): active_users is 0 or 1.",
    }
