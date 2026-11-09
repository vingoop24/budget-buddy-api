"""Budget calculations for a calendar month: totals, category limits, alerts, trends."""

import re
from calendar import monthrange
from datetime import date

from fastapi import HTTPException
from sqlmodel import Session, select

from app.config import settings
from app.models import Budget, CategoryBudget, Expense

_MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")

WARNING_PERCENT = 80
OVER_PERCENT = 100


def parse_month(month: str | None) -> tuple[date, date]:
    """Return (first_day, last_day) for 'YYYY-MM', defaulting to the current month."""
    if month is None:
        today = date.today()
        year, mon = today.year, today.month
    else:
        match = _MONTH_RE.match(month)
        if not match:
            raise HTTPException(status_code=422, detail="month must look like YYYY-MM")
        year, mon = int(match.group(1)), int(match.group(2))
    return date(year, mon, 1), date(year, mon, monthrange(year, mon)[1])


def shift_month(first_day: date, delta: int) -> date:
    index = first_day.year * 12 + (first_day.month - 1) + delta
    return date(index // 12, index % 12 + 1, 1)


def get_budget(session: Session) -> Budget:
    budget = session.get(Budget, 1)
    if budget is None:
        budget = Budget(id=1, amount=settings.default_budget, currency=settings.default_currency)
        session.add(budget)
        session.commit()
        session.refresh(budget)
    return budget


def get_category_budgets(session: Session) -> list[CategoryBudget]:
    return list(session.exec(select(CategoryBudget).order_by(CategoryBudget.category)).all())


def month_expenses(session: Session, start: date, end: date) -> list[Expense]:
    stmt = (
        select(Expense)
        .where(Expense.date >= start, Expense.date <= end)
        .order_by(Expense.date.desc(), Expense.id.desc())
    )
    return list(session.exec(stmt).all())


def _status(percent: float) -> str:
    if percent >= OVER_PERCENT:
        return "over_budget"
    if percent >= WARNING_PERCENT:
        return "warning"
    return "good"


def _money(amount: float, currency: str) -> str:
    return f"{amount:,.2f} {currency}"


def build_summary(session: Session, month: str | None) -> dict:
    start, end = parse_month(month)
    budget = get_budget(session)
    cur = budget.currency
    expenses = month_expenses(session, start, end)

    # Only expenses in the budget's currency count against the budget; others are
    # reported separately rather than silently summed with the wrong exchange rate.
    in_currency = [e for e in expenses if e.currency == cur]
    other_currency_totals: dict[str, float] = {}
    for e in expenses:
        if e.currency != cur:
            other_currency_totals[e.currency] = round(other_currency_totals.get(e.currency, 0) + e.amount, 2)

    total_spent = round(sum(e.amount for e in in_currency), 2)
    remaining = round(budget.amount - total_spent, 2)
    percent_used = round(total_spent / budget.amount * 100, 2) if budget.amount else 0.0
    status = _status(percent_used)
    advice = {
        "over_budget": "You have gone over your monthly budget.",
        "warning": "You are close to your monthly limit. Slow down non-essential spending.",
        "good": "You are in a good budget range right now.",
    }[status]

    category_totals: dict[str, float] = {}
    for e in in_currency:
        category_totals[e.category] = round(category_totals.get(e.category, 0) + e.amount, 2)
    category_totals = dict(sorted(category_totals.items(), key=lambda kv: kv[1], reverse=True))

    # Per-category limits (in the budget currency).
    category_budgets = []
    for cb in get_category_budgets(session):
        spent = category_totals.get(cb.category, 0.0)
        pct = round(spent / cb.amount * 100, 2) if cb.amount else 0.0
        category_budgets.append(
            {
                "category": cb.category,
                "limit": cb.amount,
                "spent": spent,
                "remaining": round(cb.amount - spent, 2),
                "percent_used": pct,
                "status": _status(pct),
            }
        )
    # Most urgent first.
    category_budgets.sort(key=lambda c: c["percent_used"], reverse=True)

    alerts = []
    if status == "over_budget":
        alerts.append({"level": "over", "category": None,
                       "message": f"You're {_money(-remaining, cur)} over your monthly budget."})
    elif status == "warning":
        alerts.append({"level": "warning", "category": None,
                       "message": f"You've used {percent_used:.0f}% of your monthly budget. {_money(remaining, cur)} left."})
    for c in category_budgets:
        if c["status"] == "over_budget":
            alerts.append({"level": "over", "category": c["category"],
                           "message": f"{c['category']} is {_money(-c['remaining'], cur)} over its {_money(c['limit'], cur)} limit."})
        elif c["status"] == "warning":
            alerts.append({"level": "warning", "category": c["category"],
                           "message": f"{c['category']} has used {c['percent_used']:.0f}% of its {_money(c['limit'], cur)} limit."})

    insights: list[str] = []
    if category_totals:
        top, top_amount = next(iter(category_totals.items()))
        insights.append(f"Your highest spending category is {top} at {top_amount:.2f} {cur}.")
    insights.append(f"You have used {percent_used:.0f}% of your monthly budget.")
    if remaining >= 0:
        insights.append(f"You have {remaining:.2f} {cur} left this month.")
    else:
        insights.append(f"You are {abs(remaining):.2f} {cur} over budget this month.")
    for other, amt in other_currency_totals.items():
        insights.append(f"{amt:.2f} {other} spent in {other} is not counted against your {cur} budget.")

    return {
        "month": start.strftime("%Y-%m"),
        "monthly_budget": budget.amount,
        "currency": cur,
        "total_spent": total_spent,
        "remaining": remaining,
        "percent_used": percent_used,
        "status": status,
        "advice": advice,
        "expense_count": len(expenses),
        "category_totals": category_totals,
        "category_budgets": category_budgets,
        "alerts": alerts,
        "other_currency_totals": other_currency_totals,
        "insights": insights,
        "recent_expenses": expenses[:5],
    }


def build_trends(session: Session, months: int, end_month: str | None) -> dict:
    """Total spent per month (budget currency) for the `months` months ending at end_month."""
    end_first, end_last = parse_month(end_month)
    start_first = shift_month(end_first, -(months - 1))
    budget = get_budget(session)

    # Summed in Python (not SQL date functions) so this works on any database.
    rows = session.exec(
        select(Expense.date, Expense.amount).where(
            Expense.date >= start_first, Expense.date <= end_last, Expense.currency == budget.currency
        )
    ).all()
    totals: dict[str, float] = {}
    for day, amount in rows:
        key = day.strftime("%Y-%m")
        totals[key] = totals.get(key, 0) + amount
    totals = {k: round(v, 2) for k, v in totals.items()}

    series = []
    for i in range(months):
        key = shift_month(start_first, i).strftime("%Y-%m")
        series.append({"month": key, "total_spent": totals.get(key, 0.0)})

    return {
        "currency": budget.currency,
        # The budget isn't versioned, so past months are compared to today's budget.
        "monthly_budget": budget.amount,
        "months": series,
    }
