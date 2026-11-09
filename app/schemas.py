"""Request/response bodies."""

from datetime import date as Date

from pydantic import BaseModel, Field, field_validator


def _currency(value: str) -> str:
    value = value.strip().upper()
    if len(value) != 3 or not value.isalpha():
        raise ValueError("currency must be a 3-letter code like USD or EUR")
    return value


def _required_text(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("must not be blank")
    return value


class ExpenseCreate(BaseModel):
    merchant: str = Field(max_length=200)
    charge_name: str | None = Field(default=None, max_length=200)
    amount: float = Field(gt=0, le=1_000_000)
    currency: str = "USD"
    category: str = Field(default="Other", max_length=60)
    date: Date
    payment_method: str | None = Field(default=None, max_length=60)
    notes: str | None = Field(default=None, max_length=1000)

    _merchant = field_validator("merchant", "category")(_required_text)
    _cur = field_validator("currency")(_currency)


class ExpenseUpdate(BaseModel):
    merchant: str | None = Field(default=None, max_length=200)
    charge_name: str | None = Field(default=None, max_length=200)
    amount: float | None = Field(default=None, gt=0, le=1_000_000)
    currency: str | None = None
    category: str | None = Field(default=None, max_length=60)
    date: Date | None = None
    payment_method: str | None = Field(default=None, max_length=60)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("merchant", "category")
    @classmethod
    def _text(cls, value: str | None) -> str | None:
        return None if value is None else _required_text(value)

    @field_validator("currency")
    @classmethod
    def _cur(cls, value: str | None) -> str | None:
        return None if value is None else _currency(value)


class ExpenseRead(BaseModel):
    id: int
    merchant: str
    charge_name: str | None
    amount: float
    currency: str
    category: str
    date: Date
    payment_method: str | None
    notes: str | None
    has_receipt: bool


class BudgetUpdate(BaseModel):
    amount: float = Field(gt=0, le=10_000_000)
    currency: str = "USD"

    _cur = field_validator("currency")(_currency)


class BudgetRead(BaseModel):
    amount: float
    currency: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    question: str
    response: str


class ReceiptData(BaseModel):
    merchant: str
    amount: float
    currency: str
    category: str
    date: Date
    source: str  # "ai" or "ocr"
