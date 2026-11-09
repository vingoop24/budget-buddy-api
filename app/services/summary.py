"""Budget calculations for a calendar month."""

import re
from calendar import monthrange
from datetime import date

from fastapi import HTTPException
from sqlmodel import Session, select

from app.config import settings
from app.models import Budget, Expense

_MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


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


def get_budget(session: Session) -> Budget:
    budget = session.get(Budget, 1)
    if budget is None:
        budget = Budget(id=1, amount=settings.default_budget, currency=settings.default_currency)
        session.add(budget)
        session.commit()
        session.refresh(budget)
    return budget


def month_expenses(session: Session, start: date, end: date) -> list[Expense]:
    stmt = (
        select(Expense)
        .where(Expense.date >= start, Expense.date <= end)
        .order_by(Expense.date.desc(), Expense.id.desc())
    )
    return list(session.exec(stmt).all())


def build_summary(session: Session, month: str | None) -> dict:
    start, end = parse_month(month)
    budget = get_budget(session)
    expenses = month_expenses(session, start, end)

    # Only expenses in the budget's currency count against the budget; others are
    # reported separately rather than silently summed with the wrong exchange rate.
    in_currency = [e for e in expenses if e.currency == budget.currency]
    other_currency_totals: dict[str, float] = {}
    for e in expenses:
        if e.currency != budget.currency:
            other_currency_totals[e.currency] = round(
                other_currency_totals.get(e.currency, 0) + e.amount, 2
            )

    total_spent = round(sum(e.amount for e in in_currency), 2)
    remaining = round(budget.amount - total_spent, 2)
    percent_used = round(total_spent / budget.amount * 100, 2) if budget.amount else 0.0

    category_totals: dict[str, float] = {}
    for e in in_currency:
        category_totals[e.category] = round(category_totals.get(e.category, 0) + e.amount, 2)
    category_totals = dict(sorted(category_totals.items(), key=lambda kv: kv[1], reverse=True))

    if percent_used >= 100:
        status, advice = "over_budget", "You have gone over your monthly budget."
    elif percent_used >= 80:
        status, advice = "warning", "You are close to your monthly limit. Slow down non-essential spending."
    else:
        status, advice = "good", "You are in a good budget range right now."

    insights: list[str] = []
    if category_totals:
        top, top_amount = next(iter(category_totals.items()))
        insights.append(f"Your highest spending category is {top} at {top_amount:.2f} {budget.currency}.")
    insights.append(f"You have used {percent_used:.0f}% of your monthly budget.")
    if remaining >= 0:
        insights.append(f"You have {remaining:.2f} {budget.currency} left this month.")
    else:
        insights.append(f"You are {abs(remaining):.2f} {budget.currency} over budget this month.")
    if status != "good":
        insights.append(advice)
    for cur, amt in other_currency_totals.items():
        insights.append(f"{amt:.2f} {cur} spent in {cur} is not counted against your {budget.currency} budget.")

    return {
        "month": start.strftime("%Y-%m"),
        "monthly_budget": budget.amount,
        "currency": budget.currency,
        "total_spent": total_spent,
        "remaining": remaining,
        "percent_used": percent_used,
        "status": status,
        "advice": advice,
        "expense_count": len(expenses),
        "category_totals": category_totals,
        "other_currency_totals": other_currency_totals,
        "insights": insights,
        "recent_expenses": expenses[:5],
    }
