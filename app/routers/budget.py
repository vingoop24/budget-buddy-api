from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.database import get_session
from app.routers.expenses import to_read
from app.schemas import BudgetRead, BudgetUpdate, ChatRequest, ChatResponse
from app.services import ai
from app.services.summary import build_summary, get_budget

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
