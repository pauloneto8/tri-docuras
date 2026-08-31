from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agent.llm import llm_available
from app.agent.runner import process_message
from app.auth import get_current_user, read_scope_id, require_user
from app.db import get_db
from app.models import User
from app.schemas import AgentResponse, ListTransactionsInput, SummaryInput
from app.services import finance

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/health")
async def health(db: Session = Depends(get_db)):
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        model_ready = await llm_available()
        status = "ok" if model_ready else "degraded"
    except Exception:
        status = "degraded"
    return {"status": status}


@router.get("/summary", dependencies=[Depends(require_user)])
def summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    finance.seed_defaults(db, user.id)
    return finance.get_summary(db, read_scope_id(user), SummaryInput())


@router.get("/transactions", dependencies=[Depends(require_user)])
def transactions(
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    finance.seed_defaults(db, user.id)
    return finance.list_transactions(
        db, read_scope_id(user), ListTransactionsInput(limit=limit)
    )


@router.post("/agent", response_model=AgentResponse, dependencies=[Depends(require_user)])
async def agent_api(
    message: str,
    confirmed: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    finance.seed_defaults(db, user.id)
    return await process_message(db, user.id, message, confirmed=confirmed)
