from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Category
from app.schemas import ToolCall
from app.services import finance
from app.services.agent_suggestions import for_transaction_wizard_field
from app.services.tools import (
    correct_tool_call_descriptions,
    parse_date,
    parse_user_date,
)
from app.services.text_correction import correct_movement_description
from app.timezone import local_today

WIZARD_KEY = "transaction_wizard"

SLOT_QUESTIONS = {
    "tx_type": (
        "Quer lançar uma despesa ou uma receita?\n\n"
        "Responda com *despesa* ou *receita*."
    ),
    "status": (
        "Isso já aconteceu (**realizado**) ou ainda é uma **previsão**?\n\n"
        "Responda com *realizado* ou *previsto*."
    ),
    "competence_date": (
        "Qual a *data de competência*? (a que mês o lançamento pertence)\n\n"
        "Ex.: *hoje*, *agosto* ou *01/08/2026*."
    ),
    "due_date": (
        "Qual a *data de vencimento*?\n\n"
        "Ex.: *hoje*, *amanhã* ou *10/08/2026*."
    ),
    "payment_date": (
        "Qual a *data da realização*?\n\n"
        "Ex.: *hoje*, *ontem* ou *30/08/2026*."
    ),
    "amount": "Qual o valor? (ex.: 45,90)",
    "description": "Qual a descrição? (ex.: mercado, salário, transporte)",
}

DATE_SLOTS = frozenset({"competence_date", "due_date", "payment_date"})
_DAY_ONLY_RE = re.compile(r"^(?:dia\s+)?(\d{1,2})$", re.IGNORECASE)

YES_WORDS = {"sim", "s", "ok", "confirmo", "isso", "essa", "esse"}
ACTUAL_STATUS_WORDS = {
    "realizado",
    "realizada",
    "real",
    "efetivo",
    "efetiva",
    "pago",
    "paga",
    "já aconteceu",
    "ja aconteceu",
    "actual",
    "1",
}
PLANNED_STATUS_WORDS = {
    "previsto",
    "prevista",
    "previsão",
    "previsao",
    "agendado",
    "agendada",
    "futuro",
    "planned",
    "2",
}


@dataclass
class SlotResult:
    tool_call: ToolCall | None = None
    question: str | None = None
    suggestions: list[str] | None = None


def _tx_type_from_tool(tool: str) -> str:
    return "income" if tool == "register_income" else "expense"


def list_active_account_names(db: Session, user_id: int) -> list[str]:
    accounts = db.scalars(
        select(Account)
        .where(Account.user_id == user_id, Account.is_active.is_(True))
        .order_by(Account.created_at.asc(), Account.id.asc())
    ).all()
    return [a.name for a in accounts]


def list_category_names(db: Session, user_id: int, tx_type: str) -> list[str]:
    categories = db.scalars(
        select(Category)
        .where(Category.user_id == user_id, Category.type == tx_type)
        .order_by(Category.name.asc())
    ).all()
    return [c.name for c in categories]


def infer_account_name(
    db: Session,
    user_id: int,
    message: str,
    explicit: str | None = None,
) -> str | None:
    names = list_active_account_names(db, user_id)
    if not names:
        return None

    if explicit:
        explicit = explicit.strip()
        for name in names:
            if name.lower() == explicit.lower():
                return name
        return None

    accounts = db.scalars(
        select(Account)
        .where(Account.user_id == user_id, Account.is_active.is_(True))
        .order_by(Account.created_at.asc(), Account.id.asc())
    ).all()
    if len(accounts) == 1:
        return accounts[0].name

    lower = message.lower()
    matches: list[Account] = []
    for account in accounts:
        if account.name.lower() in lower:
            matches.append(account)
            continue
        if account.institution and account.institution.lower() in lower:
            matches.append(account)

    if len(matches) == 1:
        return matches[0].name
    return None


def infer_category_name(
    db: Session,
    user_id: int,
    description: str,
    tx_type: str,
    explicit: str | None = None,
) -> str | None:
    if explicit:
        explicit = explicit.strip()
        category = finance.find_category_by_name(db, user_id, explicit, tx_type)
        if category:
            return category.name
        return None

    category = finance.suggest_category_by_keywords(db, user_id, description, tx_type)
    if category and category.name != "Outros":
        return category.name
    return None


def parse_account_answer(message: str, choices: list[str]) -> str | None:
    text = message.strip()
    if not text:
        return None
    lower = text.lower()
    for name in choices:
        if name.lower() == lower:
            return name
    for name in choices:
        if name.lower() in lower or lower in name.lower():
            return name
    return None


def parse_category_answer(
    message: str, choices: list[str], suggestion: str | None = None
) -> str | None:
    text = message.strip()
    if not text:
        return None
    lower = text.lower()
    if suggestion and lower in YES_WORDS:
        return suggestion
    for name in choices:
        if name.lower() == lower:
            return name
    for name in choices:
        if name.lower() in lower or lower in name.lower():
            return name
    return None


def parse_status_answer(message: str) -> str | None:
    lower = message.strip().lower()
    if not lower:
        return None
    if lower in ACTUAL_STATUS_WORDS:
        return "actual"
    if lower in PLANNED_STATUS_WORDS:
        return "planned"
    if any(w in lower for w in ("previsto", "prevista", "previsão", "previsao", "agendado")):
        return "planned"
    if any(w in lower for w in ("realizado", "realizada", "efetivo", "já aconteceu", "ja aconteceu")):
        return "actual"
    return None


def resolve_transaction_date(
    source_message: str,
    explicit: str | None = None,
) -> str | None:
    relative = parse_date(source_message)
    if relative:
        return relative.isoformat()
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip()
    return None


def parse_slot_date(message: str, wizard: dict | None = None) -> str | None:
    parsed = parse_user_date(message)
    if parsed:
        return parsed

    match = _DAY_ONLY_RE.fullmatch(message.strip())
    if not match:
        return None
    day = int(match.group(1))
    if day < 1 or day > 31:
        return None
    base = local_today()
    if wizard and wizard.get("competence_date"):
        try:
            base = date.fromisoformat(str(wizard["competence_date"]))
        except ValueError:
            pass
    try:
        return date(base.year, base.month, day).isoformat()
    except ValueError:
        return None


def apply_inferred_dates(wizard: dict) -> None:
    """Fill dates from an already known value; never invent today.

    Previsto: keep explicit competence/due (LLM or usuário). Do not copy
    inferred relative dates — those slots are asked.
    Realizado: payment_date (or inferred transaction_date) is copied to
    competence and due.
    """
    status = wizard.get("status")
    if not status:
        return
    inferred = wizard.get("transaction_date")

    if status == "planned":
        wizard["payment_date"] = None
        return

    payment = wizard.get("payment_date") or inferred
    if not payment:
        return
    wizard["payment_date"] = payment
    wizard["due_date"] = payment
    wizard["competence_date"] = payment
    wizard["transaction_date"] = payment


def _wizard_from_tool_call(tool_call: ToolCall, source_message: str) -> dict:
    tx_type = _tx_type_from_tool(tool_call.tool)
    args = tool_call.arguments
    description = args.get("description")
    if isinstance(description, str) and description.strip():
        description = correct_movement_description(description)
    return {
        "tx_type": tx_type,
        "amount": args.get("amount"),
        "description": description,
        "account_name": args.get("account_name"),
        "category_name": args.get("category_name"),
        "transaction_date": resolve_transaction_date(
            source_message,
            args.get("transaction_date"),
        ),
        "competence_date": args.get("competence_date"),
        "due_date": args.get("due_date"),
        "payment_date": args.get("payment_date"),
        # Sempre perguntar; não herdar status do LLM/regras.
        "status": None,
        "source_message": source_message,
        "suggested_category": None,
    }


def _tool_call_from_wizard(wizard: dict) -> ToolCall:
    tool = "register_income" if wizard["tx_type"] == "income" else "register_expense"
    args = {
        "amount": wizard["amount"],
        "description": wizard["description"],
        "account_name": wizard["account_name"],
        "category_name": wizard["category_name"],
        "status": wizard.get("status") or "actual",
    }
    for key in ("competence_date", "due_date", "payment_date", "transaction_date"):
        if wizard.get(key):
            args[key] = wizard[key]
    return correct_tool_call_descriptions(ToolCall(tool=tool, arguments=args))


def _next_slot(wizard: dict) -> str | None:
    if not wizard.get("tx_type"):
        return "tx_type"
    if not wizard.get("status"):
        return "status"
    if wizard.get("status") == "planned":
        if not wizard.get("competence_date"):
            return "competence_date"
        if not wizard.get("due_date"):
            return "due_date"
    elif wizard.get("status") == "actual":
        if not wizard.get("payment_date"):
            return "payment_date"
    if not wizard.get("amount"):
        return "amount"
    if not wizard.get("description"):
        return "description"
    if not wizard.get("account_name"):
        return "account_name"
    if not wizard.get("category_name"):
        return "category_name"
    return None


def _apply_inference(db: Session, user_id: int, wizard: dict) -> None:
    message = wizard.get("source_message") or ""
    description = wizard.get("description") or ""
    tx_type = wizard.get("tx_type") or "expense"

    if not wizard.get("transaction_date"):
        wizard["transaction_date"] = resolve_transaction_date(message)
    else:
        relative = parse_date(message)
        if relative:
            wizard["transaction_date"] = relative.isoformat()

    if not wizard.get("account_name"):
        inferred = infer_account_name(
            db, user_id, message, wizard.get("account_name")
        )
        if inferred:
            wizard["account_name"] = inferred

    if not wizard.get("category_name") and description:
        inferred = infer_category_name(
            db,
            user_id,
            description,
            tx_type,
            wizard.get("category_name"),
        )
        if inferred:
            wizard["category_name"] = inferred
            wizard["suggested_category"] = inferred
        else:
            suggested = infer_category_name(db, user_id, description, tx_type)
            if suggested:
                wizard["suggested_category"] = suggested

    apply_inferred_dates(wizard)


def _question_for_slot(
    db: Session, user_id: int, wizard: dict, slot: str
) -> str:
    if slot in SLOT_QUESTIONS:
        return SLOT_QUESTIONS[slot]
    tx_type = wizard.get("tx_type") or "expense"
    if slot == "account_name":
        names = list_active_account_names(db, user_id)
        joined = ", ".join(names) if names else "nenhuma"
        return f"Em qual conta registrar? Você tem: {joined}."
    if slot == "category_name":
        names = list_category_names(db, user_id, tx_type)
        joined = ", ".join(names) if names else "nenhuma"
        suggestion = wizard.get("suggested_category")
        if suggestion:
            return (
                f"Qual categoria? Sugestão pelo contexto: *{suggestion}*. "
                f"Opções: {joined}. Responda com o nome ou *sim* para aceitar a sugestão."
            )
        return f"Qual categoria? Opções: {joined}."
    return "Informe o dado solicitado."


def fill_slot(wizard: dict, slot: str, message: str, db: Session, user_id: int) -> str | None:
    tx_type = wizard.get("tx_type") or "expense"
    if slot == "status":
        parsed = parse_status_answer(message)
        if not parsed:
            return "Responda com *realizado* ou *previsto*."
        wizard["status"] = parsed
        return None
    if slot in DATE_SLOTS:
        parsed = parse_slot_date(message, wizard)
        if not parsed:
            return (
                "Data inválida. Informe como *hoje*, *ontem* ou *31/08/2026*."
            )
        wizard[slot] = parsed
        if slot == "payment_date":
            wizard["competence_date"] = parsed
            wizard["due_date"] = parsed
            wizard["transaction_date"] = parsed
        return None
    if slot == "account_name":
        choices = list_active_account_names(db, user_id)
        parsed = parse_account_answer(message, choices)
        if not parsed:
            return f"Conta inválida. Escolha uma das opções: {', '.join(choices)}."
        wizard["account_name"] = parsed
        return None
    if slot == "category_name":
        choices = list_category_names(db, user_id, tx_type)
        parsed = parse_category_answer(
            message, choices, wizard.get("suggested_category")
        )
        if not parsed:
            return f"Categoria inválida. Escolha uma das opções: {', '.join(choices)}."
        wizard["category_name"] = parsed
        return None
    return "Campo desconhecido."


def ensure_transaction_slots(
    db: Session,
    user_id: int,
    session: dict,
    tool_call: ToolCall,
    source_message: str,
) -> SlotResult:
    new_wizard = _wizard_from_tool_call(tool_call, source_message)
    wizard = session.get(WIZARD_KEY)
    if not wizard:
        wizard = new_wizard
    elif wizard.get("amount") is None:
        wizard = new_wizard
    elif _next_slot(wizard) is None:
        wizard = new_wizard
    elif new_wizard.get("amount") and wizard.get("amount") != new_wizard.get("amount"):
        wizard = new_wizard
    session[WIZARD_KEY] = wizard

    _apply_inference(db, user_id, wizard)
    session[WIZARD_KEY] = wizard

    slot = _next_slot(wizard)
    if slot is None:
        return SlotResult(tool_call=_tool_call_from_wizard(wizard))

    return SlotResult(
        question=_question_for_slot(db, user_id, wizard, slot),
        suggestions=for_transaction_wizard_field(slot, db, user_id, wizard),
    )


def process_slot_answer(
    db: Session, user_id: int, session: dict, message: str
) -> SlotResult:
    wizard = session.get(WIZARD_KEY)
    if not wizard:
        return SlotResult()

    slot = _next_slot(wizard)
    if slot in {"status", "account_name", "category_name"} | DATE_SLOTS:
        error = fill_slot(wizard, slot, message, db, user_id)
        if error:
            return SlotResult(
                question=error,
                suggestions=for_transaction_wizard_field(slot, db, user_id, wizard),
            )
        session[WIZARD_KEY] = wizard
        _apply_inference(db, user_id, wizard)
        session[WIZARD_KEY] = wizard
        slot = _next_slot(wizard)
        if slot is None:
            return SlotResult(tool_call=_tool_call_from_wizard(wizard))
        return SlotResult(
            question=_question_for_slot(db, user_id, wizard, slot),
            suggestions=for_transaction_wizard_field(slot, db, user_id, wizard),
        )

    return SlotResult()
