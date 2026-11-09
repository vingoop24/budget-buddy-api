from fastapi import APIRouter, Depends, File, UploadFile
from sqlmodel import Session

from app.database import get_session
from app.models import Expense
from app.routers.expenses import to_read
from app.schemas import ReceiptData
from app.services import receipts
from app.services.summary import get_budget

router = APIRouter(tags=["receipts"])


@router.post("/scan-receipt", response_model=ReceiptData)
def scan_receipt(receipt: UploadFile = File(...), session: Session = Depends(get_session)):
    """Extract fields from a receipt for the user to review. No expense is created;
    the image is held for 24h and attached when the returned `receipt_token` is
    sent with POST /expenses."""
    data, ext, mime = receipts.read_image(receipt)
    extracted = receipts.extract(data, mime, get_budget(session).currency)
    return {**extracted, "receipt_token": receipts.save_pending(data, ext)}


@router.post("/scan-and-save-receipt", status_code=201)
def scan_and_save_receipt(receipt: UploadFile = File(...), session: Session = Depends(get_session)):
    """Extract fields from a receipt and save it as a new expense with the image attached."""
    data, ext, mime = receipts.read_image(receipt)
    extracted = receipts.extract(data, mime, get_budget(session).currency)

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
    session.commit()
    session.refresh(expense)
    return {"expense": to_read(expense), "source": extracted["source"]}
