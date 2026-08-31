from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Account, Category, Transaction, User
from app.schemas import BudgetStatusInput, ListTransactionsInput, SummaryInput
from app.services import finance


def list_users_overview(db: Session) -> list[dict]:
    users = db.scalars(select(User).order_by(User.created_at.desc())).all()
    results = []
    for user in users:
        tx_count = db.scalar(
            select(func.count()).select_from(Transaction).where(Transaction.user_id == user.id)
        )
        account_count = db.scalar(
            select(func.count()).select_from(Account).where(Account.user_id == user.id)
        )
        results.append(
            {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "is_active": user.is_active,
                "is_root": user.is_root,
                "onboarding_completed": user.onboarding_completed,
                "transactions": int(tx_count or 0),
                "accounts": int(account_count or 0),
                "created_at": user.created_at,
            }
        )
    return results


def get_user_detail(db: Session, user_id: int) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    categories = db.scalars(
        select(Category)
        .where(Category.user_id == user.id)
        .order_by(Category.type.asc(), Category.name.asc())
    ).all()

    return {
        "profile": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "is_active": user.is_active,
            "is_root": user.is_root,
            "onboarding_completed": user.onboarding_completed,
            "created_at": user.created_at,
        },
        "summary": finance.get_summary(db, user.id, SummaryInput()),
        "accounts": finance.account_balances(db, user.id),
        "transactions": finance.list_transactions(
            db, user.id, ListTransactionsInput(limit=50)
        ),
        "budgets": finance.get_budget_status(db, user.id, BudgetStatusInput()),
        "categories": [
            {"id": c.id, "name": c.name, "type": c.type} for c in categories
        ],
    }


def set_user_active(db: Session, user_id: int, *, active: bool) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    if user.is_root and not active:
        raise HTTPException(status_code=400, detail="Não é possível desativar um administrador root.")
    user.is_active = active
    db.commit()
    db.refresh(user)
    return user
