"""Slots para pagamento de fatura de cartão no assistente."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, CreditCard
from app.schemas import ToolCall
from app.services.agent_suggestions import for_pay_invoice_field
from app.services.credit_cards import parse_invoice_period_hint, preview_payable_invoice
from app.services.transaction_slots import (
    infer_card_name,
    parse_account_answer,
)
from app.services.tools import parse_date

WIZARD_KEY = "pay_invoice_wizard"

QUESTIONS = {
    "account_name": "Qual cartão deseja pagar a fatura?",
    "from_account_name": "De qual conta sairá o pagamento?",
    "payment_date": "Qual a data do pagamento? (ex.: hoje, ontem, 01/09/2026)",
}


@dataclass
class SlotResult:
    tool_call: ToolCall | None = None
    question: str | None = None
    suggestions: list[str] | None = None


def get_wizard(session: dict) -> dict | None:
    return session.get(WIZARD_KEY)


def clear_wizard(session: dict) -> None:
    session.pop(WIZARD_KEY, None)


def _list_card_names(db: Session, user_id: int) -> list[str]:
    rows = db.scalars(
        select(CreditCard.name).where(
            CreditCard.user_id == user_id,
            CreditCard.is_active.is_(True),
        )
    ).all()
    return list(rows)


def _list_debit_names(db: Session, user_id: int) -> list[str]:
    rows = db.scalars(
        select(Account.name).where(
            Account.user_id == user_id,
            Account.is_active.is_(True),
            Account.account_type != "cartao",
        )
    ).all()
    return list(rows)


def _name_in_list(name: str | None, choices: list[str]) -> bool:
    if not name:
        return False
    lower = name.strip().lower()
    return any(choice.lower() == lower for choice in choices)


def _sanitize_wizard_names(db: Session, user_id: int, wizard: dict) -> None:
    cards = _list_card_names(db, user_id)
    debits = _list_debit_names(db, user_id)
    if wizard.get("account_name") and not _name_in_list(wizard["account_name"], cards):
        wizard.pop("account_name", None)
        wizard.pop("invoice_id", None)
    if wizard.get("from_account_name") and not _name_in_list(
        wizard["from_account_name"], debits
    ):
        wizard.pop("from_account_name", None)


def _enrich_wizard_invoice(db: Session, user_id: int, wizard: dict) -> None:
    preview = preview_payable_invoice(
        db,
        user_id,
        invoice_id=wizard.get("invoice_id"),
        card_name=wizard.get("account_name"),
        due_month=wizard.get("due_month"),
        due_year=wizard.get("due_year"),
    )
    if not preview:
        wizard.pop("invoice_id", None)
        wizard.pop("invoice_total", None)
        wizard.pop("invoice_due_label", None)
        wizard.pop("invoice_planned_count", None)
        return
    wizard["invoice_id"] = preview["id"]
    wizard["account_name"] = preview["card_name"]
    wizard["invoice_total"] = preview["total"]
    wizard["invoice_due_label"] = preview["due_date_label"]
    wizard["invoice_planned_count"] = preview.get("planned_count", 0)
    settlement = preview.get("settlement_account_name")
    if settlement and not wizard.get("from_account_name"):
        wizard["from_account_name"] = settlement


def _start_wizard(session: dict, tool_call: ToolCall) -> dict:
    args = tool_call.arguments
    data = {
        "invoice_id": args.get("invoice_id"),
        "account_name": args.get("account_name"),
        "from_account_name": args.get("from_account_name"),
        "payment_date": args.get("payment_date"),
        "due_month": args.get("due_month"),
        "due_year": args.get("due_year"),
    }
    session[WIZARD_KEY] = data
    return data


def _invoice_summary_line(wizard: dict) -> str:
    if not wizard.get("invoice_total"):
        return ""
    parts = [
        f"*{wizard.get('account_name') or 'Cartão'}*: {wizard['invoice_total']}",
        f"venc. {wizard.get('invoice_due_label', '')}",
    ]
    planned = int(wizard.get("invoice_planned_count") or 0)
    if planned:
        parts.append(f"{planned} lançamento(s) previsto(s) serão liquidados")
    return " — ".join(parts[:2]) + (f" ({parts[2]})" if len(parts) > 2 else "")


def _question_for_field(
    field: str, db: Session, user_id: int, wizard: dict
) -> str:
    summary = _invoice_summary_line(wizard)
    if field == "account_name":
        if summary:
            return f"{QUESTIONS[field]}\n\nFatura identificada: {summary}."
        return QUESTIONS[field]
    if field == "from_account_name":
        if summary:
            return f"Fatura: {summary}.\n\n{QUESTIONS[field]}"
        return QUESTIONS[field]
    if field == "payment_date":
        if summary:
            return f"Fatura: {summary}.\n\n{QUESTIONS[field]}"
        return QUESTIONS[field]
    return QUESTIONS.get(field, "")


def _next_field(wizard: dict) -> str | None:
    if not wizard.get("account_name") and wizard.get("invoice_id") is None:
        return "account_name"
    if not wizard.get("from_account_name"):
        return "from_account_name"
    if not wizard.get("payment_date_asked"):
        return "payment_date"
    return None


def _wizard_to_tool_call(wizard: dict) -> ToolCall:
    args = {
        "from_account_name": wizard["from_account_name"],
    }
    if wizard.get("invoice_id") is not None:
        args["invoice_id"] = wizard["invoice_id"]
    if wizard.get("account_name"):
        args["account_name"] = wizard["account_name"]
    if wizard.get("payment_date"):
        args["payment_date"] = wizard["payment_date"]
    if wizard.get("due_month") is not None:
        args["due_month"] = wizard["due_month"]
    if wizard.get("due_year") is not None:
        args["due_year"] = wizard["due_year"]
    if wizard.get("invoice_total"):
        args["invoice_total"] = wizard["invoice_total"]
    if wizard.get("invoice_due_label"):
        args["invoice_due_label"] = wizard["invoice_due_label"]
    return ToolCall(tool="pay_invoice", arguments=args)


def _apply_message_hints(
    db: Session, user_id: int, wizard: dict, message: str
) -> None:
    cards = _list_card_names(db, user_id)
    debits = _list_debit_names(db, user_id)

    if not wizard.get("account_name"):
        inferred = infer_card_name(db, user_id, message)
        if inferred:
            wizard["account_name"] = inferred
        elif len(cards) == 1 and (wizard.get("due_month") or wizard.get("invoice_id")):
            wizard["account_name"] = cards[0]

    if not wizard.get("from_account_name"):
        parsed = parse_account_answer(message, debits)
        if parsed:
            wizard["from_account_name"] = parsed
        else:
            lower = message.lower()
            matches = [name for name in debits if name.lower() in lower]
            if len(matches) == 1:
                wizard["from_account_name"] = matches[0]

    period = parse_invoice_period_hint(message)
    if period:
        wizard["due_month"], wizard["due_year"] = period

    if not wizard.get("payment_date"):
        parsed = parse_date(message)
        if parsed:
            wizard["payment_date"] = parsed.isoformat()


def ensure_pay_invoice_slots(
    db: Session,
    user_id: int,
    session: dict,
    tool_call: ToolCall,
    message: str,
) -> SlotResult:
    wizard = get_wizard(session) or _start_wizard(session, tool_call)
    _sanitize_wizard_names(db, user_id, wizard)
    _apply_message_hints(db, user_id, wizard, message)
    _sanitize_wizard_names(db, user_id, wizard)
    _enrich_wizard_invoice(db, user_id, wizard)
    session[WIZARD_KEY] = wizard

    field = _next_field(wizard)
    if field:
        return SlotResult(
            question=_question_for_field(field, db, user_id, wizard),
            suggestions=for_pay_invoice_field(field, db, user_id, wizard),
        )
    return SlotResult(tool_call=_wizard_to_tool_call(wizard))


def try_process_pay_invoice_wizard(
    session: dict, message: str, *, db: Session, user_id: int
) -> SlotResult | None:
    wizard = get_wizard(session)
    if not wizard:
        return None

    field = _next_field(wizard)
    if not field:
        return SlotResult(tool_call=_wizard_to_tool_call(wizard))

    if field == "account_name":
        cards = _list_card_names(db, user_id)
        parsed = parse_account_answer(message, cards)
        if not parsed:
            return SlotResult(
                question="Cartão inválido. Informe o nome do cartão.",
                suggestions=for_pay_invoice_field(field, db, user_id, wizard),
            )
        wizard["account_name"] = parsed
    elif field == "from_account_name":
        debits = _list_debit_names(db, user_id)
        parsed = parse_account_answer(message, debits)
        if not parsed:
            lower = message.lower()
            matches = [name for name in debits if name.lower() in lower]
            if len(matches) == 1:
                parsed = matches[0]
        if not parsed:
            return SlotResult(
                question="Conta inválida. Informe a conta de débito.",
                suggestions=for_pay_invoice_field(field, db, user_id, wizard),
            )
        wizard["from_account_name"] = parsed
    elif field == "payment_date":
        wizard["payment_date_asked"] = True
        lower = message.strip().lower()
        if lower in {"hoje", "ontem", "pular", "agora"}:
            if lower == "pular":
                wizard["payment_date"] = None
            else:
                parsed = parse_date(message)
                wizard["payment_date"] = parsed.isoformat() if parsed else None
        else:
            from app.services.tools import parse_user_date

            parsed = parse_user_date(message)
            if not parsed:
                return SlotResult(
                    question="Data inválida. Use *hoje*, *ontem* ou *DD/MM/AAAA*.",
                    suggestions=for_pay_invoice_field(field, db, user_id, wizard),
                )
            wizard["payment_date"] = parsed.isoformat()

    session[WIZARD_KEY] = wizard
    _enrich_wizard_invoice(db, user_id, wizard)
    session[WIZARD_KEY] = wizard
    remaining = _next_field(wizard)
    if remaining:
        return SlotResult(
            question=_question_for_field(remaining, db, user_id, wizard),
            suggestions=for_pay_invoice_field(remaining, db, user_id, wizard),
        )
    return SlotResult(tool_call=_wizard_to_tool_call(wizard))
