from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session, col, func, select

from app.database import get_session
from app.models import CATEGORIES, Expense
from app.schemas import ExpenseCreate, ExpenseRead, ExpenseUpdate
from app.services import receipts
from app.services.summary import parse_month

router = APIRouter(tags=["expenses"])


def to_read(expense: Expense) -> ExpenseRead:
    return ExpenseRead(
        **expense.model_dump(exclude={"receipt_image", "created_at"}),
        has_receipt=bool(expense.receipt_image),
    )


def get_or_404(session: Session, expense_id: int) -> Expense:
    expense = session.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found")
    return expense


@router.get("/categories", response_model=list[str])
def list_categories(session: Session = Depends(get_session)):
    """Default categories followed by any custom ones already used."""
    used = session.exec(select(Expense.category).distinct()).all()
    return CATEGORIES + sorted(c for c in used if c not in CATEGORIES)


@router.get("/expenses", response_model=list[ExpenseRead])
def list_expenses(
    month: str | None = Query(default=None, description="YYYY-MM; omit for all time"),
    category: str | None = None,
    q: str | None = Query(default=None, description="Search merchant and notes"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    stmt = select(Expense)
    if month:
        start, end = parse_month(month)
        stmt = stmt.where(Expense.date >= start, Expense.date <= end)
    if category:
        stmt = stmt.where(Expense.category == category)
    if q:
        pattern = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            func.lower(Expense.merchant).like(pattern) | func.lower(col(Expense.notes)).like(pattern)
        )
    stmt = stmt.order_by(Expense.date.desc(), Expense.id.desc()).offset(offset).limit(limit)
    return [to_read(e) for e in session.exec(stmt).all()]


@router.post("/expenses", response_model=ExpenseRead, status_code=201)
def create_expense(body: ExpenseCreate, session: Session = Depends(get_session)):
    expense = Expense(**body.model_dump(exclude={"receipt_token"}))
    if body.receipt_token:
        expense.receipt_image = receipts.claim_pending(body.receipt_token)
    session.add(expense)
    try:
        session.commit()
    except Exception:
        receipts.delete_image(expense.receipt_image)
        raise
    session.refresh(expense)
    return to_read(expense)


@router.get("/expenses/{expense_id}", response_model=ExpenseRead)
def get_expense(expense_id: int, session: Session = Depends(get_session)):
    return to_read(get_or_404(session, expense_id))


@router.patch("/expenses/{expense_id}", response_model=ExpenseRead)
def update_expense(expense_id: int, body: ExpenseUpdate, session: Session = Depends(get_session)):
    expense = get_or_404(session, expense_id)
    changes = body.model_dump(exclude_unset=True)
    for required in ("merchant", "amount", "currency", "category", "date"):
        if required in changes and changes[required] is None:
            raise HTTPException(status_code=422, detail=f"{required} cannot be null")
    for key, value in changes.items():
        setattr(expense, key, value)
    session.add(expense)
    session.commit()
    session.refresh(expense)
    return to_read(expense)


@router.delete("/expenses/{expense_id}", status_code=204)
def delete_expense(expense_id: int, session: Session = Depends(get_session)):
    expense = get_or_404(session, expense_id)
    image = expense.receipt_image
    session.delete(expense)
    session.commit()
    receipts.delete_image(image)
    return Response(status_code=204)


@router.post("/expenses/{expense_id}/receipt", response_model=ExpenseRead)
def upload_receipt(
    expense_id: int, receipt: UploadFile = File(...), session: Session = Depends(get_session)
):
    expense = get_or_404(session, expense_id)
    data, ext, _ = receipts.read_image(receipt)
    old = expense.receipt_image
    expense.receipt_image = receipts.save_image(data, ext)
    session.add(expense)
    session.commit()
    session.refresh(expense)
    receipts.delete_image(old)
    return to_read(expense)


@router.get("/expenses/{expense_id}/receipt")
def view_receipt(expense_id: int, session: Session = Depends(get_session)):
    expense = get_or_404(session, expense_id)
    if not expense.receipt_image:
        raise HTTPException(status_code=404, detail="No receipt linked to this expense")
    return FileResponse(receipts.receipt_path(expense.receipt_image))
