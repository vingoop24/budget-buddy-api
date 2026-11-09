"""Database tables."""

from datetime import date as Date
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


CATEGORIES = [
    "Food & Dining",
    "Groceries",
    "Transport",
    "Travel",
    "Shopping",
    "Entertainment",
    "Bills & Utilities",
    "Health",
    "Other",
]


class Expense(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    merchant: str
    charge_name: str | None = None  # Name shown on the bank statement
    amount: float
    currency: str = "USD"
    category: str = Field(default="Other", index=True)
    date: Date = Field(index=True)
    payment_method: str | None = None
    receipt_image: str | None = None  # Stored file name inside the receipt folder
    notes: str | None = None
    created_at: datetime = Field(default_factory=_now)


class Budget(SQLModel, table=True):
    """Single-row table (id=1) holding the user's monthly budget."""

    id: int = Field(default=1, primary_key=True)
    amount: float
    currency: str = "USD"


class CategoryBudget(SQLModel, table=True):
    """Monthly spending limit for one category, in the main budget's currency."""

    category: str = Field(primary_key=True, max_length=60)
    amount: float
