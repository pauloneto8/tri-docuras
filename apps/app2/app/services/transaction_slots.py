from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Category, CreditCard
from app.schemas import ToolCall, decimal_to_cents, format_brl
from app.services import finance
from app.services.agent_suggestions import for_transaction_wizard_field
from app.services.tools import (
    correct_tool_call_descriptions,
    parse_date,
    parse_user_date,
)
from app.services.text_correction import correct_movement_description
from app.services.installments import (
    parse_installment_count,
    parse_installment_interval,
    parse_installment_start_index,
    split_cents,
)
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
    "payment_mode": (
        "Esse lançamento é **único**, **fixo** (repete) ou **parcelado**?\n\n"
        "Responda com *único*, *fixo* ou *parcelado*."
    ),
    "payment_source": (
        "Esse lançamento é no **cartão de crédito** ou em **conta bancária**?\n\n"
        "Responda com *cartão* ou *conta*."
    ),
    "frequency": (
        "Com que frequência esse lançamento se repete?\n\n"
        "Responda com *diária*, *semanal* ou *mensal*."
    ),
    "recurrence_end_date": (
        "Tem *data de término* para essa série?\n\n"
        "Responda *não* ou informe a data (ex.: *31/12/2026*)."
    ),
    "installment_count": (
        "Em quantas vezes? (mínimo 2)\n\n"
        "Ex.: *12*, *12x* ou *6 vezes*."
    ),
    "installment_interval": (
        "Qual o intervalo entre as parcelas?\n\n"
        "Responda *mensal*, *semanal* ou *quinzenal*."
    ),
    "installment_start_index": (
        "É a **primeira parcela** ou você já está em outra?\n\n"
        "Informe *1* para a primeira ou o número da parcela atual (ex.: *3* de 12)."
    ),
    "amount": "Qual o valor? (ex.: 45,90)",
    "description": "Qual a descrição? (ex.: mercado, salário, transporte)",
    "card_name": (
        "Em qual **cartão de crédito** registrar?\n\n"
        "Responda com o nome do cartão cadastrado."
    ),
}

DATE_SLOTS = frozenset({"competence_date", "due_date", "payment_date"})
RECURRENCE_SLOTS = frozenset({"frequency", "recurrence_end_date"})
INSTALLMENT_SLOTS = frozenset({
    "installment_count",
    "installment_interval",
    "installment_start_index",
    "installment_amount_basis",
})
MODE_SLOTS = frozenset({"payment_mode"})
PAYMENT_SOURCE_SLOTS = frozenset({"payment_source"})
_DAY_ONLY_RE = re.compile(r"^(?:dia\s+)?(\d{1,2})$", re.IGNORECASE)
_SAME_DATE_RE = re.compile(
    r"^(?:tamb[ée]m|mesm[oa]|igual|a mesma|na mesma|mesma data|idem)\b",
    re.IGNORECASE,
)

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


def wants_card_payment(message: str) -> bool:
    lower = message.lower()
    return "cartão" in lower or "cartao" in lower


def list_active_card_names(db: Session, user_id: int) -> list[str]:
    cards = db.scalars(
        select(CreditCard)
        .where(CreditCard.user_id == user_id, CreditCard.is_active.is_(True))
        .order_by(CreditCard.created_at.asc(), CreditCard.id.asc())
    ).all()
    return [c.name for c in cards]


def _normalize_card_reference(name: str) -> str:
    return re.sub(r"^(do|da|de)\s+", "", name.strip(), flags=re.IGNORECASE).strip(" .,-")


def infer_card_name(
    db: Session,
    user_id: int,
    message: str,
    explicit: str | None = None,
) -> str | None:
    names = list_active_card_names(db, user_id)
    if not names:
        return None

    if explicit:
        explicit = explicit.strip()
        for name in names:
            if name.lower() == explicit.lower():
                return name
        return None

    from app.services.intents import _extract_card_reference

    ref = _extract_card_reference(message)
    if ref:
        ref = _normalize_card_reference(ref)
        ref_short = re.split(
            r"\s+(?:a|de|da|do|para)\s+",
            ref,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(" .,-")
        if ref_short:
            for name in names:
                if name.lower() == ref_short.lower():
                    return name
            for name in names:
                if ref_short.lower() in name.lower() or name.lower() in ref_short.lower():
                    return name

    lower = message.lower()
    matches: list[str] = []
    for name in names:
        if name.lower() in lower:
            matches.append(name)
    if len(matches) == 1:
        return matches[0]
    return None


def resolve_card_settlement_account_name(
    db: Session, user_id: int, card_name: str,
) -> str | None:
    try:
        card = finance.resolve_card_for_transaction(db, user_id, card_name)
    except ValueError:
        return None
    if not card.settlement_account_id:
        return None
    account = db.get(Account, card.settlement_account_id)
    if not account or not account.is_active:
        return None
    return account.name


def _is_card_payment_wizard(wizard: dict) -> bool:
    if wizard.get("payment_source") == "card":
        return True
    if wizard.get("payment_source") == "account":
        return False
    if wizard.get("card_name"):
        return True
    if wizard.get("payment_on_card"):
        return True
    return wants_card_payment(wizard.get("source_message") or "")


def _apply_card_planned_defaults(wizard: dict) -> None:
    """Compra no cartão é prevista até o pagamento da fatura — não movimenta caixa."""
    if wizard.get("tx_type") == "expense" and _is_card_payment_wizard(wizard):
        wizard["status"] = "planned"
        wizard["payment_date"] = None


def _should_skip_due_date_slot(wizard: dict) -> bool:
    return _is_card_payment_wizard(wizard)


def _purchase_anchor_date(wizard: dict) -> date | None:
    for key in ("payment_date", "competence_date", "transaction_date"):
        raw = wizard.get(key)
        if not raw:
            continue
        try:
            return date.fromisoformat(str(raw))
        except ValueError:
            continue
    return None


def _apply_card_due_dates(db: Session, user_id: int, wizard: dict) -> None:
    if wizard.get("payment_source") != "card":
        return
    card_name = wizard.get("card_name")
    purchase = _purchase_anchor_date(wizard)
    if not purchase:
        return
    try:
        card = finance.resolve_card_for_transaction(db, user_id, card_name)
    except ValueError:
        return
    from app.services.credit_cards import cycle_for_purchase

    _, _, invoice_due = cycle_for_purchase(card.closing_day, card.due_day, purchase)
    wizard["due_date"] = invoice_due.isoformat()


def _ensure_card_settlement_account(db: Session, user_id: int, wizard: dict) -> None:
    if not wizard.get("card_name"):
        return
    if wizard.get("account_name"):
        return
    settlement = resolve_card_settlement_account_name(
        db, user_id, wizard["card_name"]
    )
    if settlement:
        wizard["account_name"] = settlement


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


def parse_slot_date(
    message: str,
    wizard: dict | None = None,
    *,
    slot: str | None = None,
) -> str | None:
    if slot == "due_date" and wizard and wizard.get("competence_date"):
        lower = message.strip().lower()
        if _SAME_DATE_RE.search(lower):
            rest = _SAME_DATE_RE.sub("", lower).strip(" .,-")
            if not rest or rest in {"data", "a data", "à data"}:
                return str(wizard["competence_date"])
            same_parsed = parse_user_date(rest)
            if same_parsed:
                return same_parsed

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
    competence and due — exceto em parcelamento, onde as datas são sempre
    perguntadas explicitamente.
    """
    status = wizard.get("status")
    if not status:
        return
    if wizard.get("payment_mode") == "installment":
        return
    if wizard.get("payment_mode") is None:
        return
    inferred = wizard.get("transaction_date")
    if status == "planned":
        wizard["payment_date"] = None
        return

    payment = wizard.get("payment_date") or inferred
    if not payment:
        return
    wizard["payment_date"] = payment
    wizard["competence_date"] = payment
    wizard["transaction_date"] = payment
    if not _is_card_payment_wizard(wizard):
        wizard["due_date"] = payment


def _clear_installment_schedule_dates(wizard: dict) -> None:
    wizard["competence_date"] = None
    wizard["due_date"] = None
    wizard["payment_date"] = None


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
        "card_name": args.get("card_name"),
        "payment_source": None,
        "payment_on_card": False,
        "has_credit_cards": False,
        "category_name": args.get("category_name"),
        "transaction_date": resolve_transaction_date(
            source_message,
            args.get("transaction_date"),
        ),
        # Sempre perguntar; não herdar datas nem status do LLM/regras.
        "competence_date": None,
        "due_date": None,
        "payment_date": None,
        "status": None,
        "payment_mode": _infer_payment_mode(args),
        "is_recurring": None,
        "frequency": args.get("frequency"),
        "recurrence_end_date": args.get("recurrence_end_date"),
        "recurrence_end_asked": bool(args.get("recurrence_end_date")),
        "installment_count": args.get("installment_count"),
        "installment_interval": args.get("installment_interval"),
        "installment_start_index": None,
        "installment_amount_basis": None,
        "source_message": source_message,
        "suggested_category": None,
    }


def _tool_call_from_wizard(wizard: dict) -> ToolCall:
    tool = "register_income" if wizard["tx_type"] == "income" else "register_expense"
    _apply_card_planned_defaults(wizard)
    args = {
        "amount": wizard["amount"],
        "description": wizard["description"],
        "category_name": wizard["category_name"],
        "status": wizard.get("status") or "actual",
    }
    if wizard.get("card_name"):
        args["card_name"] = wizard["card_name"]
    if wizard.get("account_name"):
        args["account_name"] = wizard["account_name"]
    for key in ("competence_date", "due_date", "payment_date", "transaction_date"):
        if wizard.get(key):
            args[key] = wizard[key]
    if wizard.get("payment_mode") == "fixed" and wizard.get("frequency"):
        args["frequency"] = wizard["frequency"]
        if wizard.get("recurrence_end_date"):
            args["recurrence_end_date"] = wizard["recurrence_end_date"]
    if wizard.get("payment_mode") == "installment":
        if wizard.get("installment_count"):
            args["installment_count"] = wizard["installment_count"]
        if wizard.get("installment_interval"):
            args["installment_interval"] = wizard["installment_interval"]
        if wizard.get("installment_start_index"):
            args["installment_start_index"] = wizard["installment_start_index"]
        if wizard.get("installment_amount_basis"):
            args["installment_amount_basis"] = wizard["installment_amount_basis"]
    return correct_tool_call_descriptions(ToolCall(tool=tool, arguments=args))


def _infer_payment_mode(args: dict) -> str | None:
    if args.get("installment_count"):
        return "installment"
    if args.get("frequency"):
        return "fixed"
    return None


def refresh_wizard_payment_context(db: Session, user_id: int, wizard: dict) -> None:
    wizard["has_credit_cards"] = bool(list_active_card_names(db, user_id))
    if wizard.get("tx_type") == "expense" and not wizard["has_credit_cards"]:
        wizard["payment_source"] = "account"
        wizard["payment_on_card"] = False


def _needs_payment_source(wizard: dict) -> bool:
    if wizard.get("tx_type") != "expense":
        return False
    if wizard.get("payment_source") is not None:
        return False
    return bool(wizard.get("has_credit_cards"))


def parse_payment_source_answer(message: str) -> str | None:
    lower = message.strip().lower()
    if not lower:
        return None
    if lower in {
        "cartão",
        "cartao",
        "crédito",
        "credito",
        "cartão de crédito",
        "cartao de credito",
        "2",
    }:
        return "card"
    if lower in {
        "conta",
        "bancária",
        "bancaria",
        "débito",
        "debito",
        "conta bancária",
        "conta bancaria",
        "pix",
        "1",
    }:
        return "account"
    if "cart" in lower or "crédit" in lower or "credit" in lower:
        return "card"
    if any(word in lower for word in ("conta", "débito", "debito", "pix", "dinheiro")):
        return "account"
    return None


def _next_slot(wizard: dict) -> str | None:
    if not wizard.get("tx_type"):
        return "tx_type"
    if _needs_payment_source(wizard):
        return "payment_source"
    _apply_card_planned_defaults(wizard)
    if not wizard.get("status"):
        return "status"
    if wizard.get("payment_source") == "card" and not wizard.get("card_name"):
        return "card_name"
    if wizard.get("status") == "planned":
        if wizard.get("payment_mode") != "installment":
            if not wizard.get("competence_date"):
                return "competence_date"
            if not wizard.get("due_date") and not _should_skip_due_date_slot(wizard):
                return "due_date"
    elif wizard.get("status") == "actual":
        if wizard.get("payment_mode") is None:
            return "payment_mode"
        if wizard.get("payment_mode") != "installment" and not wizard.get("payment_date"):
            return "payment_date"
    if wizard.get("payment_mode") is None:
        return "payment_mode"
    if wizard.get("payment_mode") == "fixed":
        if not wizard.get("frequency"):
            return "frequency"
        if not wizard.get("recurrence_end_asked"):
            return "recurrence_end_date"
    if wizard.get("payment_mode") == "installment":
        if not wizard.get("installment_count"):
            return "installment_count"
        if not wizard.get("installment_interval"):
            return "installment_interval"
        if not wizard.get("installment_start_index"):
            return "installment_start_index"
        if not wizard.get("competence_date"):
            return "competence_date"
        if not wizard.get("due_date") and not _should_skip_due_date_slot(wizard):
            return "due_date"
        if wizard.get("status") == "actual" and not wizard.get("payment_date"):
            return "payment_date"
    if not wizard.get("amount"):
        return "amount"
    if wizard.get("payment_mode") == "installment" and not wizard.get(
        "installment_amount_basis"
    ):
        return "installment_amount_basis"
    if not wizard.get("description"):
        return "description"
    if not wizard.get("card_name") and not wizard.get("account_name"):
        if wizard.get("payment_source") == "card":
            return "card_name"
        if wizard.get("payment_source") == "account":
            return "account_name"
        return "account_name"
    if not wizard.get("category_name"):
        return "category_name"
    return None


def _apply_inference(db: Session, user_id: int, wizard: dict) -> None:
    from app.services.tools import extract_description, parse_amount

    message = wizard.get("source_message") or ""
    description = wizard.get("description") or ""
    tx_type = wizard.get("tx_type") or "expense"

    if not wizard.get("amount"):
        inferred_amount = parse_amount(message.lower())
        if inferred_amount:
            wizard["amount"] = inferred_amount
            if not description:
                description = extract_description(message, inferred_amount)
                wizard["description"] = description
    if not wizard.get("description") and wizard.get("amount"):
        inferred_desc = extract_description(message, wizard["amount"])
        if inferred_desc and inferred_desc != "Lançamento":
            wizard["description"] = inferred_desc
            description = inferred_desc

    if not wizard.get("transaction_date"):
        wizard["transaction_date"] = resolve_transaction_date(message)
    else:
        relative = parse_date(message)
        if relative:
            wizard["transaction_date"] = relative.isoformat()

    payment_source = wizard.get("payment_source")
    if payment_source == "card":
        wizard["payment_on_card"] = True
        if not wizard.get("card_name"):
            inferred = infer_card_name(db, user_id, message, wizard.get("card_name"))
            if inferred:
                wizard["card_name"] = inferred
        wizard.pop("account_name", None)
        _ensure_card_settlement_account(db, user_id, wizard)
        _apply_card_planned_defaults(wizard)
    elif payment_source == "account":
        wizard["payment_on_card"] = False
        wizard.pop("card_name", None)
        if not wizard.get("account_name"):
            inferred = infer_account_name(
                db, user_id, message, wizard.get("account_name")
            )
            if inferred:
                wizard["account_name"] = inferred
    elif not wizard.get("account_name"):
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
    _apply_card_due_dates(db, user_id, wizard)


def parse_installment_amount_basis(message: str) -> str | None:
    lower = message.strip().lower()
    if not lower:
        return None
    if lower in {"total", "valor total", "da compra", "dividir"}:
        return "total"
    if lower in {"parcela", "valor da parcela", "cada parcela", "da parcela"}:
        return "installment"
    if "valor total" in lower or "da compra" in lower or "dividir" in lower:
        return "total"
    if any(
        phrase in lower
        for phrase in ("valor da parcela", "cada parcela", "da parcela")
    ):
        return "installment"
    return None


def _question_installment_amount_basis(wizard: dict) -> str:
    amount_str = str(wizard.get("amount") or "0")
    count = int(wizard.get("installment_count") or 2)
    amount_cents = decimal_to_cents(amount_str)
    per_cents = split_cents(amount_cents, count)[0]
    total_if_unit_cents = amount_cents * count
    br_amount = format_brl(amount_cents)
    br_per = format_brl(per_cents)
    br_total_unit = format_brl(total_if_unit_cents)
    return (
        f"Os **R$ {br_amount}** são o **valor total** da compra "
        f"({count} parcelas de cerca de R$ {br_per}) ou o **valor de cada parcela** "
        f"({count} × R$ {br_amount} = R$ {br_total_unit})?"
    )


def _question_installment_competence_date(wizard: dict) -> str:
    idx = wizard.get("installment_start_index") or 1
    total = wizard.get("installment_count") or "?"
    return (
        f"Qual a *competência* da parcela *{idx}/{total}* que você está lançando?\n\n"
        "Ex.: *hoje*, *agosto* ou *01/09/2026*."
    )


def _question_installment_due_date(wizard: dict) -> str:
    idx = wizard.get("installment_start_index") or 1
    total = wizard.get("installment_count") or "?"
    return (
        f"Qual o *vencimento* da parcela *{idx}/{total}*?\n\n"
        "As demais parcelas serão calculadas a partir desta data.\n\n"
        "Ex.: *hoje*, *amanhã* ou *10/09/2026*."
    )


def _question_for_slot(
    db: Session, user_id: int, wizard: dict, slot: str
) -> str:
    if slot == "installment_amount_basis":
        return _question_installment_amount_basis(wizard)
    if slot == "competence_date" and wizard.get("payment_mode") == "installment":
        return _question_installment_competence_date(wizard)
    if slot == "due_date" and wizard.get("payment_mode") == "installment":
        return _question_installment_due_date(wizard)
    if slot in SLOT_QUESTIONS:
        return SLOT_QUESTIONS[slot]
    tx_type = wizard.get("tx_type") or "expense"
    if slot == "account_name":
        names = list_active_account_names(db, user_id)
        joined = ", ".join(names) if names else "nenhuma"
        return f"Em qual conta registrar? Você tem: {joined}."
    if slot == "card_name":
        names = list_active_card_names(db, user_id)
        joined = ", ".join(names) if names else "nenhum"
        return f"Em qual cartão registrar? Você tem: {joined}."
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


def parse_payment_mode_answer(message: str) -> str | None:
    from app.services.installments import parse_installment_count

    lower = message.strip().lower()
    if lower in {"único", "unico", "avulso", "única", "unica", "não", "nao", "n", "no", "1"}:
        return "single"
    if lower in {"fixo", "fixa", "recorrente", "repete", "sim", "s"}:
        return "fixed"
    if lower in {"parcelado", "parcelada", "parcelas", "parcela", "parcelamento"}:
        return "installment"
    if parse_installment_count(message):
        return "installment"
    return None


def parse_is_recurring_answer(message: str) -> bool | None:
    lower = message.strip().lower()
    if lower in {"sim", "s", "yes", "fixo", "fixa", "repete", "recorrente"}:
        return True
    if lower in {"não", "nao", "n", "no", "único", "unico", "avulso"}:
        return False
    return None


def fill_slot(wizard: dict, slot: str, message: str, db: Session, user_id: int) -> str | None:
    tx_type = wizard.get("tx_type") or "expense"
    if slot == "status":
        parsed = parse_status_answer(message)
        if not parsed:
            return "Responda com *realizado* ou *previsto*."
        wizard["status"] = parsed
        return None
    if slot == "payment_source":
        parsed = parse_payment_source_answer(message)
        if not parsed:
            return "Responda com *cartão* ou *conta*."
        wizard["payment_source"] = parsed
        if parsed == "account":
            wizard["payment_on_card"] = False
            wizard.pop("card_name", None)
            wizard.pop("due_date", None)
        else:
            wizard["payment_on_card"] = True
            wizard.pop("account_name", None)
        _apply_card_planned_defaults(wizard)
        return None
    if slot in DATE_SLOTS:
        parsed = parse_slot_date(message, wizard, slot=slot)
        if not parsed:
            return (
                "Data inválida. Informe como *hoje*, *ontem* ou *31/08/2026*."
            )
        wizard[slot] = parsed
        if slot == "payment_date":
            wizard["transaction_date"] = parsed
            if wizard.get("payment_mode") != "installment":
                wizard["competence_date"] = parsed
                if not _is_card_payment_wizard(wizard):
                    wizard["due_date"] = parsed
        elif slot == "competence_date" and _is_card_payment_wizard(wizard):
            wizard.pop("due_date", None)
        return None
    if slot == "payment_mode":
        parsed = parse_payment_mode_answer(message)
        if parsed is None:
            return "Responda com *único*, *fixo* ou *parcelado*."
        wizard["payment_mode"] = parsed
        wizard["is_recurring"] = parsed == "fixed"
        if parsed == "single":
            wizard["frequency"] = None
            wizard["recurrence_end_date"] = None
            wizard["recurrence_end_asked"] = True
            wizard["installment_count"] = None
            wizard["installment_interval"] = None
            wizard["installment_start_index"] = None
            wizard["installment_amount_basis"] = None
        elif parsed == "fixed":
            wizard["installment_count"] = None
            wizard["installment_interval"] = None
            wizard["installment_start_index"] = None
            wizard["installment_amount_basis"] = None
        else:
            wizard["frequency"] = None
            wizard["recurrence_end_date"] = None
            wizard["recurrence_end_asked"] = True
            wizard["payment_date"] = None
            count = parse_installment_count(message)
            if count:
                wizard["installment_count"] = count
        return None
    if slot == "is_recurring":
        parsed = parse_is_recurring_answer(message)
        if parsed is None:
            return "Responda com *sim* ou *não*."
        wizard["is_recurring"] = parsed
        if not parsed:
            wizard["frequency"] = None
            wizard["recurrence_end_date"] = None
            wizard["recurrence_end_asked"] = True
        return None
    if slot == "frequency":
        from app.services.recurrence import parse_frequency

        parsed = parse_frequency(message)
        if not parsed:
            return "Frequência inválida. Use *diária*, *semanal* ou *mensal*."
        wizard["frequency"] = parsed
        return None
    if slot == "installment_count":
        parsed = parse_installment_count(message)
        if not parsed:
            return "Informe o número de parcelas (mínimo 2). Ex.: *12* ou *12x*."
        wizard["installment_count"] = parsed
        return None
    if slot == "installment_interval":
        parsed = parse_installment_interval(message)
        if not parsed:
            return "Intervalo inválido. Use *mensal*, *semanal* ou *quinzenal*."
        wizard["installment_interval"] = parsed
        return None
    if slot == "installment_start_index":
        max_count = int(wizard.get("installment_count") or 2)
        parsed = parse_installment_start_index(message, max_count)
        if not parsed:
            return (
                f"Informe a parcela atual de *1* a *{max_count}* "
                "(ex.: *1* para a primeira ou *3* para a terceira)."
            )
        wizard["installment_start_index"] = parsed
        return None
    if slot == "installment_amount_basis":
        parsed = parse_installment_amount_basis(message)
        if not parsed:
            return (
                "Responda se o valor informado é o *valor total* da compra "
                "ou o *valor de cada parcela*."
            )
        wizard["installment_amount_basis"] = parsed
        return None
    if slot == "recurrence_end_date":
        lower = message.strip().lower()
        if lower in {"não", "nao", "n", "no", "sem", "nunca"}:
            wizard["recurrence_end_date"] = None
            wizard["recurrence_end_asked"] = True
            return None
        parsed = parse_slot_date(message, wizard, slot=slot)
        if not parsed:
            return "Data inválida. Responda *não* ou informe a data."
        wizard["recurrence_end_date"] = parsed
        wizard["recurrence_end_asked"] = True
        return None
    if slot == "account_name":
        choices = list_active_account_names(db, user_id)
        parsed = parse_account_answer(message, choices)
        if not parsed:
            return f"Conta inválida. Escolha uma das opções: {', '.join(choices)}."
        wizard["account_name"] = parsed
        return None
    if slot == "card_name":
        choices = list_active_card_names(db, user_id)
        parsed = parse_account_answer(message, choices)
        if not parsed:
            return f"Cartão inválido. Escolha uma das opções: {', '.join(choices)}."
        wizard["card_name"] = parsed
        wizard.pop("account_name", None)
        _ensure_card_settlement_account(db, user_id, wizard)
        _apply_card_due_dates(db, user_id, wizard)
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
    refresh_wizard_payment_context(db, user_id, new_wizard)
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
    refresh_wizard_payment_context(db, user_id, wizard)
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
    if slot in {"status", "account_name", "card_name", "category_name"} | DATE_SLOTS | MODE_SLOTS | PAYMENT_SOURCE_SLOTS | RECURRENCE_SLOTS | INSTALLMENT_SLOTS:
        error = fill_slot(wizard, slot, message, db, user_id)
        if error:
            return SlotResult(
                question=error,
                suggestions=for_transaction_wizard_field(slot, db, user_id, wizard),
            )
        session[WIZARD_KEY] = wizard
        _apply_inference(db, user_id, wizard)
        refresh_wizard_payment_context(db, user_id, wizard)
        session[WIZARD_KEY] = wizard
        slot = _next_slot(wizard)
        if slot is None:
            return SlotResult(tool_call=_tool_call_from_wizard(wizard))
        return SlotResult(
            question=_question_for_slot(db, user_id, wizard, slot),
            suggestions=for_transaction_wizard_field(slot, db, user_id, wizard),
        )

    return SlotResult()
