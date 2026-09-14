"""Fase 4 do plano de inteligência proativa: memória de personalização.

Aprende categoria e/ou forma de pagamento (cartão vs conta) de descrições
recorrentes de lançamentos manuais confirmados pelo chat — nunca decidido pelo
LLM. Regra 100% determinística e derivada de `Transaction` já gravada:

- Só oferece lembrar quando a mesma descrição (normalizada) já apareceu
  exatamente 3 vezes seguidas com a mesma categoria e/ou forma de pagamento.
- Só grava com resposta explícita "sim" do usuário (nunca sozinho).
- "não" (ou qualquer resposta que não seja um sim claro) apenas fecha a
  pergunta — na próxima vez que o padrão se repetir (4ª, 5ª...) não
  pergunta de novo, pois a checagem exige contagem exatamente igual a 3.

Leitura (`lookup_description_preference`) é usada em `transaction_slots.py`
para pré-preencher categoria/forma de pagamento sem perguntar de novo — a
confirmação de escrita continua obrigatória como qualquer outro lançamento.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, AgentDescriptionPreference, Category, CreditCard, Transaction
from app.schemas import AgentResponse
from app.services.statement_parse import normalize_memo

PENDING_KEY = "pending_description_preference"
MATCH_THRESHOLD = 3

_YES = {"sim", "s", "yes", "pode", "pode sim", "isso", "confirma", "claro", "combinado", "ok"}
_NO = {"não", "nao", "n", "no", "não precisa", "nao precisa", "deixa", "deixa pra lá", "deixa pra la"}


def _lookup_by_key(
    db: Session, user_id: int, key: str
) -> AgentDescriptionPreference | None:
    if not key:
        return None
    rows = db.scalars(
        select(AgentDescriptionPreference).where(
            AgentDescriptionPreference.user_id == user_id,
            AgentDescriptionPreference.description_key == key,
        )
    ).all()
    return rows[0] if rows else None


def lookup_description_preference(
    db: Session, user_id: int, description: str
) -> AgentDescriptionPreference | None:
    return _lookup_by_key(db, user_id, normalize_memo(description or ""))


def _matching_history(
    db: Session, user_id: int, tx_type: str, key: str
) -> list[Transaction]:
    txs = db.scalars(
        select(Transaction)
        .where(Transaction.user_id == user_id, Transaction.type == tx_type)
        .order_by(Transaction.id.asc())
    ).all()
    return [t for t in txs if normalize_memo(t.description) == key]


def maybe_offer_description_preference(
    db: Session,
    session: dict,
    *,
    user_id: int,
    tx_type: str,
    description: str,
    category_id: int | None,
    card_id: int | None,
    account_id: int | None,
) -> str | None:
    """Depois de um register_expense/register_income confirmado (não
    recorrente, não parcelado), sugere lembrar categoria e/ou forma de
    pagamento se este for o 3º lançamento seguido com o mesmo padrão. Só
    pergunta — nunca salva sozinho. Retorna o texto a anexar à resposta, ou
    None quando não há nada a oferecer."""
    key = normalize_memo(description or "")
    if not key or tx_type not in {"expense", "income"}:
        return None
    if _lookup_by_key(db, user_id, key):
        return None  # já lembrado — não pergunta de novo

    matches = _matching_history(db, user_id, tx_type, key)
    if len(matches) != MATCH_THRESHOLD:
        return None

    same_category = bool(category_id) and all(
        t.category_id == category_id for t in matches
    )
    payment_source = "card" if card_id else ("account" if account_id else None)
    same_payment = payment_source is not None and all(
        (t.card_id == card_id and t.account_id == account_id) for t in matches
    )

    parts: list[str] = []
    if same_category:
        category = db.get(Category, category_id)
        if category:
            parts.append(f"categorizar sempre como **{category.name}**")
        else:
            same_category = False
    if same_payment:
        if payment_source == "card":
            card = db.get(CreditCard, card_id)
            if card:
                parts.append(f"lançar sempre no cartão **{card.name}**")
            else:
                same_payment = False
        else:
            account = db.get(Account, account_id)
            if account:
                parts.append(f"lançar sempre na conta **{account.name}**")
            else:
                same_payment = False

    if not parts:
        return None

    session[PENDING_KEY] = {
        "description_key": key,
        "category_id": category_id if same_category else None,
        "payment_source": payment_source if same_payment else None,
        "card_id": card_id if same_payment and payment_source == "card" else None,
        "account_id": account_id if same_payment and payment_source == "account" else None,
    }
    joined = " e ".join(parts)
    return (
        f"\n\nNotei que você lançou \"{description}\" assim 3 vezes seguidas. "
        f"Quer que eu passe a {joined} automaticamente da próxima vez? (sim/não)"
    )


def offer_description_preference_from_result(
    db: Session, session: dict, user_id: int, tool: str, result
) -> str | None:
    """Wrapper chamado nos dois pontos onde register_expense/register_income
    são efetivamente executados (`app/agent/runner.py` e
    `app/routers/pages.py`): filtra para o caso simples (um lançamento único,
    não recorrente, não parcelado) antes de chamar
    `maybe_offer_description_preference`."""
    if tool not in {"register_expense", "register_income"}:
        return None
    if not isinstance(result, dict) or not result.get("id"):
        return None
    if result.get("recurrence_id") or result.get("installment_plan_id"):
        return None
    return maybe_offer_description_preference(
        db,
        session,
        user_id=user_id,
        tx_type=result.get("type"),
        description=result.get("description") or "",
        category_id=result.get("category_id"),
        card_id=result.get("card_id"),
        account_id=result.get("account_id"),
    )


def try_process_pending_description_preference(
    session: dict,
    message: str,
    db: Session,
    user_id: int,
) -> AgentResponse | None:
    pending = session.get(PENDING_KEY)
    if not pending:
        return None

    lower = message.strip().lower()
    session.pop(PENDING_KEY, None)

    if lower in _YES:
        existing = _lookup_by_key(db, user_id, pending["description_key"])
        if existing:
            existing.category_id = pending.get("category_id") or existing.category_id
            existing.payment_source = pending.get("payment_source") or existing.payment_source
            existing.card_id = pending.get("card_id") or existing.card_id
            existing.account_id = pending.get("account_id") or existing.account_id
        else:
            db.add(
                AgentDescriptionPreference(
                    user_id=user_id,
                    description_key=pending["description_key"],
                    category_id=pending.get("category_id"),
                    payment_source=pending.get("payment_source"),
                    card_id=pending.get("card_id"),
                    account_id=pending.get("account_id"),
                )
            )
        db.commit()
        return AgentResponse(
            message="Combinado, vou lembrar disso da próxima vez.",
            source="preference",
        )

    if lower in _NO:
        return AgentResponse(
            message="Ok, não vou lembrar automaticamente.",
            source="preference",
        )

    # Mensagem não relacionada: não bloqueia o usuário, só encerra a
    # pergunta em aberto e deixa o fluxo normal tratar a mensagem.
    return None
