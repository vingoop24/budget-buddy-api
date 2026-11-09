from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlmodel import Session

from app.database import get_session
from app.routers.expenses import to_read
from app.models import CategoryBudget
from app.schemas import (
    BudgetRead,
    BudgetUpdate,
    CategoryBudgetRead,
    CategoryBudgetUpdate,
    ChatRequest,
    ChatResponse,
)
from app.services import ai
from app.services.summary import build_summary, build_trends, get_budget, get_category_budgets

router = APIRouter(tags=["budget"])


@router.get("/budget", response_model=BudgetRead)
def read_budget(session: Session = Depends(get_session)):
    return get_budget(session)


@router.put("/budget", response_model=BudgetRead)
def update_budget(body: BudgetUpdate, session: Session = Depends(get_session)):
    budget = get_budget(session)
    budget.amount = body.amount
    budget.currency = body.currency
    session.add(budget)
    session.commit()
    session.refresh(budget)
    return budget


@router.get("/category-budgets", response_model=list[CategoryBudgetRead])
def list_category_budgets(session: Session = Depends(get_session)):
    return get_category_budgets(session)


@router.put("/category-budgets/{category}", response_model=CategoryBudgetRead)
def set_category_budget(
    body: CategoryBudgetUpdate,
    category: str = Path(min_length=1, max_length=60),
    session: Session = Depends(get_session),
):
    category = category.strip()
    if not category:
        raise HTTPException(status_code=422, detail="category must not be blank")
    item = session.get(CategoryBudget, category) or CategoryBudget(category=category, amount=body.amount)
    item.amount = body.amount
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.delete("/category-budgets/{category}", status_code=204)
def delete_category_budget(category: str, session: Session = Depends(get_session)):
    item = session.get(CategoryBudget, category)
    if item is None:
        raise HTTPException(status_code=404, detail="No limit set for this category")
    session.delete(item)
    session.commit()
    return Response(status_code=204)


@router.get("/trends")
def trends(
    months: int = Query(default=6, ge=1, le=24),
    end: str | None = Query(default=None, description="YYYY-MM; defaults to the current month"),
    session: Session = Depends(get_session),
):
    return build_trends(session, months, end)


@router.get("/summary")
def summary(
    month: str | None = Query(default=None, description="YYYY-MM; defaults to the current month"),
    session: Session = Depends(get_session),
):
    data = build_summary(session, month)
    data["recent_expenses"] = [to_read(e) for e in data["recent_expenses"]]
    return data


# Kept for older clients; same payload as /summary.
router.add_api_route("/ai-insights", summary, methods=["GET"], include_in_schema=False)


@router.post("/ai-assistant", response_model=ChatResponse, tags=["ai"])
def ai_assistant(chat: ChatRequest, session: Session = Depends(get_session)):
    answer = ai.ask_assistant(chat.question, build_summary(session, None))
    return ChatResponse(question=chat.question, response=answer)
