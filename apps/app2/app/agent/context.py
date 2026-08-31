"""Monta contexto dinâmico para o LLM de intenção."""

from __future__ import annotations

from app.schemas import ListTransactionsInput
from app.services import finance
from app.services.account_wizard import get_wizard_context as get_account_wizard_context
from app.services.category_wizard import get_wizard_context as get_category_wizard_context
from app.services.conversations import SESSION_CONVERSATION_KEY, get_recent_messages
from app.services.transaction_wizard import get_wizard_context as get_transaction_wizard_context


def build_intent_context(
    db,
    user_id: int,
    session: dict,
) -> str:
    parts: list[str] = []

    tx_ctx = get_transaction_wizard_context(session)
    if tx_ctx:
        parts.append(tx_ctx)
    acc_ctx = get_account_wizard_context(session)
    if acc_ctx:
        parts.append(acc_ctx)
    cat_ctx = get_category_wizard_context(session)
    if cat_ctx:
        parts.append(cat_ctx)

    accounts = finance.account_balances(db, user_id)
    if accounts:
        lines = [
            f"- id={acc['id']} {acc['account']} ({acc['account_type_label']})"
            + (f", {acc['institution']}" if acc.get("institution") else "")
            + f", saldo_inicial=R$ {acc['opening_balance']}"
            + (
                f", data_saldo_inicial={acc['opening_balance_date_label']}"
                if acc.get("opening_balance_date_label")
                else ", data_saldo_inicial=nao informada"
            )
            + f", saldo_atual=R$ {acc['balance']}"
            for acc in accounts
        ]
        parts.append("Contas do usuario:\n" + "\n".join(lines))

    categories = finance.list_user_categories(db, user_id)
    if categories:
        lines = [
            f"- id={cat['id']} {cat['name']} ({cat['type_label']})"
            + (f", keywords={cat['keywords']}" if cat.get("keywords") else "")
            for cat in categories
        ]
        parts.append("Categorias do usuario:\n" + "\n".join(lines))

    transactions = finance.list_transactions(
        db, user_id, ListTransactionsInput(limit=8, type="all")
    )
    if transactions:
        lines = [
            (
                f"- id={tx['id']} {tx['type']} R$ {tx['amount']} "
                f"'{tx['description']}' conta={tx['account']} "
                f"categoria={tx['category']} data={tx['transaction_date']}"
            )
            for tx in transactions
        ]
        parts.append("Ultimos lancamentos:\n" + "\n".join(lines))

    conv_id = session.get(SESSION_CONVERSATION_KEY)
    if conv_id:
        messages = get_recent_messages(db, user_id, conv_id, limit=4)
        if messages:
            history = "\n".join(
                f"{msg.role}: {msg.content[:300]}" for msg in messages
            )
            parts.append(f"Historico recente da conversa:\n{history}")

    return "\n\n".join(parts)
