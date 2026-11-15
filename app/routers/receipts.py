import time

from fastapi import APIRouter, Depends, File, UploadFile
from sqlmodel import Session

from app.database import get_session
from app.models import Expense
from app.routers.expenses import to_read
from app.schemas import ReceiptData
from app.config import settings
from app.services import events, receipts
from app.services.summary import get_budget

router = APIRouter(tags=["receipts"])


def _extract_and_record(session: Session, data: bytes, mime: str) -> dict:
    started = time.perf_counter()
    extracted = receipts.extract(data, mime, get_budget(session).currency)
    events.record(
        session, "scan_completed",
        source=extracted["source"], missing=extracted["missing"],
        duration_ms=round((time.perf_counter() - started) * 1000),
        model=settings.openai_model if extracted["source"] == "ai" else None,
    )
    return extracted


@router.post("/scan-receipt", response_model=ReceiptData)
def scan_receipt(receipt: UploadFile = File(...), session: Session = Depends(get_session)):
    """Extract fields from a receipt for the user to review. No expense is created;
    the image is held for 24h and attached when the returned `receipt_token` is
    sent with POST /expenses."""
    data, ext, mime = receipts.read_image(receipt)
    extracted = _extract_and_record(session, data, mime)
    session.commit()
    return {**extracted, "receipt_token": receipts.save_pending(data, ext, extracted)}


@router.post("/scan-and-save-receipt", status_code=201)
def scan_and_save_receipt(receipt: UploadFile = File(...), session: Session = Depends(get_session)):
    """Extract fields from a receipt and save it as a new expense with the image attached."""
    data, ext, mime = receipts.read_image(receipt)
    extracted = _extract_and_record(session, data, mime)

    expense = Expense(
        merchant=extracted["merchant"],
        amount=extracted["amount"],
        currency=extracted["currency"],
        category=extracted["category"],
        date=extracted["date"],
        receipt_image=receipts.save_image(data, ext),
        notes=f"Created from receipt scan ({extracted['source']})",
    )
    session.add(expense)
    session.flush()
    events.record(session, "expense_created", expense.id, source="scan",
                  category=expense.category, currency=expense.currency)
    session.commit()
    session.refresh(expense)
    return {"expense": to_read(expense), "source": extracted["source"]}
