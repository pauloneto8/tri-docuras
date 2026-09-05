import json
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from app.schemas import (
    BudgetStatusInput,
    CreateAccountInput,
    CreateCardInput,
    CreateCategoryInput,
    DeleteTransactionInput,
    DeleteCardInput,
    ListTransactionsInput,
    PayInvoiceInput,
    RegisterExpenseInput,
    RegisterIncomeInput,
    RegisterTransferInput,
    RealizePlannedInput,
    SummaryInput,
    ToolCall,
    UpdateAccountInput,
    UpdateCardInput,
    UpdateTransactionInput,
    UpdateTransferInput,
    decimal_to_cents,
)
from app.services import finance
from app.services.intents import (
    detect_category_creation,
    detect_planned_movement,
    detect_transfer,
    wants_category_creation,
    wants_list_accounts,
    wants_list_categories,
    wants_planned_movement,
    wants_realize_planned,
    wants_register_expense,
    wants_register_income,
    wants_transfer,
    wants_transfer_correction,
)
from app.services.text_correction import correct_category_name, correct_movement_description
from app.timezone import local_today


AMOUNT_RE = re.compile(
    r"(?:r\$\s*)?(\d{1,3}(?:\.\d{3})*,\d{2}|\d+(?:[.,]\d{1,2})?)",
    re.IGNORECASE,
)
EXPENSE_HINTS = ("gastei", "paguei", "comprei", "gasto", "despesa", "debito")
INCOME_HINTS = ("recebi", "ganhei", "entrada", "salario", "salário", "credito", "crédito")
LIST_HINTS = ("ultimas", "últimas", "listar", "extrato", "historico", "histórico")
SUMMARY_HINTS = ("resumo", "balanco", "balanço", "quanto gastei", "quanto recebi")
BUDGET_HINTS = ("orcamento", "orçamento", "limite", "budget")
CORRECTION_HINTS = (
    "corrija",
    "corrigir",
    "correção",
    "correcao",
    "editar",
    "edite",
    "alterar",
    "altere",
    "altera",
    "mudar",
    "mude",
    "trocar",
    "troque",
    "atualizar",
    "atualize",
    "atualiza",
)
DELETE_HINTS = ("excluir", "exclua", "deletar", "delete", "apagar", "apague", "remover", "remova")
DESCRIPTION_TOOLS = {"register_expense", "register_income", "update_transaction"}
OPENING_BALANCE_HINTS = ("saldo inicial", "saldo de abertura")
OPENING_DATE_HINTS = (
    "data do saldo inicial",
    "data do saldo",
    "a partir de",
    "desde",
    "válido em",
    "valido em",
    "válida em",
    "valida em",
)
ACCOUNT_UPDATE_HINTS = CORRECTION_HINTS + (
    "altere",
    "altera",
    "tem",
    "era",
    "é",
    "e ",
    "mudar",
    "mude",
    "colocar",
    "definir",
    "atualizar",
    "atualize",
)
ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
BR_DATE_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")
MONTHS_PT = {
    "janeiro": 1,
    "fevereiro": 2,
    "março": 3,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}
ACCOUNT_NAME_HINTS = (
    ("mercado pago", "Mercado Pago"),
    ("nubank", "Nubank"),
    ("itau", "Itaú"),
    ("itaú", "Itaú"),
    ("bradesco", "Bradesco"),
    ("santander", "Santander"),
    ("caixa", "Caixa"),
    ("inter", "Inter"),
    ("banco do brasil", "BB"),
    ("carteira", "Carteira"),
)


def _extract_account_name(text: str) -> str | None:
    lower = text.lower()
    for hint, label in ACCOUNT_NAME_HINTS:
        if hint in lower:
            return label
    return None


def parse_amount(text: str) -> str | None:
    match = AMOUNT_RE.search(text)
    if not match:
        return None
    raw = match.group(1)
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(",", ".")
    try:
        decimal_to_cents(raw)
        return raw
    except (InvalidOperation, ValueError):
        return None


def parse_date(text: str) -> date | None:
    lower = text.lower()
    today = local_today()
    if "ontem" in lower:
        return today - timedelta(days=1)
    if "hoje" in lower:
        return today
    if "amanhã" in lower or "amanha" in lower:
        return today + timedelta(days=1)
    return None


def is_relative_date_message(message: str) -> bool:
    lower = message.lower().strip()
    if parse_date(lower) is None:
        return False
    if not any(token in lower for token in ("ontem", "hoje", "amanhã", "amanha")):
        return False
    return len(strip_relative_date_tokens(message)) < 2


def is_date_only_message(message: str) -> bool:
    """True when the user message is only a date (not an expense narrative)."""
    stripped = message.strip()
    if not stripped or parse_user_date(stripped) is None:
        return False
    lower = stripped.lower()
    if any(h in lower for h in EXPENSE_HINTS + INCOME_HINTS):
        return False
    if "despesa" in lower or "receita" in lower:
        return False
    if BR_DATE_RE.fullmatch(stripped) or ISO_DATE_RE.fullmatch(stripped):
        return True
    if is_relative_date_message(stripped):
        return True
    # Month name or short phrase without amounts (agosto, 1 de agosto de 2026)
    if len(list(AMOUNT_RE.finditer(stripped))) >= 2:
        return False
    return len(stripped.split()) <= 6


_RELATIVE_DATE_TOKEN_RE = re.compile(r"\b(?:ontem|hoje|amanh[ãa])\b", re.IGNORECASE)
_RELATIVE_DATE_PHRASE_RE = re.compile(
    r"^\s*(?:foi|era|é|e|no dia|a despesa foi|despesa foi)\s+",
    re.IGNORECASE,
)


def strip_relative_date_tokens(text: str) -> str:
    cleaned = _RELATIVE_DATE_PHRASE_RE.sub("", text.strip())
    cleaned = _RELATIVE_DATE_TOKEN_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -,.")
    return cleaned


def parse_user_date(text: str) -> str | None:
    parsed = parse_date(text)
    if parsed:
        return parsed.isoformat()

    iso_match = ISO_DATE_RE.search(text)
    if iso_match:
        return f"{iso_match.group(1)}-{iso_match.group(2)}-{iso_match.group(3)}"

    br_match = BR_DATE_RE.search(text)
    if br_match:
        day = int(br_match.group(1))
        month = int(br_match.group(2))
        year = int(br_match.group(3))
        if year < 100:
            year += 2000
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None

    lower = text.lower()
    for month_name, month_num in MONTHS_PT.items():
        pattern = rf"(\d{{1,2}})\s+de\s+{month_name}(?:\s+de\s+(\d{{4}}))?"
        match = re.search(pattern, lower)
        if match:
            day = int(match.group(1))
            year = int(match.group(2)) if match.group(2) else local_today().year
            try:
                return date(year, month_num, day).isoformat()
            except ValueError:
                return None

    stripped = text.strip().lower()
    for month_name, month_num in MONTHS_PT.items():
        match = re.fullmatch(rf"{month_name}(?:\s+de\s+(\d{{4}}))?$", stripped)
        if match:
            year = int(match.group(1)) if match.group(1) else local_today().year
            return date(year, month_num, 1).isoformat()
        match = re.fullmatch(rf"{month_name}/(\d{{4}})$", stripped)
        if match:
            return date(int(match.group(1)), month_num, 1).isoformat()

    return None


def parse_opening_balance_date(text: str) -> str | None:
    return parse_user_date(text)


DESCRIPTION_PREP_RE = re.compile(
    r"\b(?:referente\s+(?:a|ao|à|aos|às)|com|em|de|para)\s+(.+)$",
    re.IGNORECASE,
)

UPDATE_DESCRIPTION_RE = re.compile(
    r"(?:descri[cç][aã]o|descricao).{0,40}?\bpara\b\s+(.+)$"
    r"|(?:despesa|receita|lan[cç]amento).{0,40}?\bpara\b\s+(.+)$",
    re.IGNORECASE,
)


def extract_description(text: str, amount: str | None) -> str:
    desc = text.strip()
    if amount:
        desc = re.sub(re.escape(amount), "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"r\$\s*", "", desc, flags=re.IGNORECASE)

    referente = re.search(
        r"\breferente\s+(?:a|ao|à|aos|às)\s+(.+)$",
        desc,
        re.IGNORECASE,
    )
    if referente:
        candidate = referente.group(1).strip(" -,.")
        if candidate and len(candidate) >= 2:
            return candidate[:255]

    prep_match = DESCRIPTION_PREP_RE.search(desc)
    if prep_match:
        candidate = prep_match.group(1).strip(" -,.")
        if candidate and len(candidate) >= 2:
            # Evita pegar só "594 referente..." quando o "de" antecede o valor já removido
            if not re.match(r"^(?:referente|r\$)\b", candidate, re.IGNORECASE):
                return candidate[:255]
            if candidate.lower().startswith("referente"):
                rest = re.sub(
                    r"^referente\s+(?:a|ao|à|aos|às)\s+",
                    "",
                    candidate,
                    flags=re.IGNORECASE,
                ).strip(" -,.")
                if len(rest) >= 2:
                    return rest[:255]

    for token in (
        *EXPENSE_HINTS,
        *INCOME_HINTS,
        "eu",
        "ontem",
        "hoje",
        "lance",
        "lançar",
        "lancar",
        "receita",
        "despesa",
        "uma",
        "um",
    ):
        desc = re.sub(rf"\b{re.escape(token)}\b", "", desc, flags=re.IGNORECASE)
    desc = re.sub(r"\s+", " ", desc).strip(" -,.")
    return desc or "Lançamento"


def try_rule_based_parse(message: str) -> ToolCall | None:
    lower = message.lower().strip()
    amount = parse_amount(lower)

    from app.services.intents import (
        detect_card_delete,
        detect_card_update,
        wants_card_delete,
        wants_card_update,
    )

    if wants_card_delete(message):
        return ToolCall(tool="delete_card", arguments=detect_card_delete(message) or {})

    if wants_card_update(message):
        data = detect_card_update(message) or {}
        if data.get("card_name") and any(
            key for key in data if key not in {"card_name"}
        ):
            return ToolCall(tool="update_card", arguments=data)

    if any(h in lower for h in DELETE_HINTS):
        args: dict = {}
        if amount:
            args["amount"] = amount
        for keyword in ("passagem", "passagens", "mercado", "transporte", "salário", "salario"):
            if keyword in lower:
                args["description"] = keyword
                break
        return ToolCall(tool="delete_transaction", arguments=args)

    if (
        any(h in lower for h in OPENING_BALANCE_HINTS + OPENING_DATE_HINTS)
        and any(h in lower for h in ACCOUNT_UPDATE_HINTS)
    ):
        args: dict = {}
        if amount:
            args["opening_balance"] = amount
        opening_date = parse_opening_balance_date(message)
        if opening_date:
            args["opening_balance_date"] = opening_date
        account_name = _extract_account_name(lower)
        if account_name:
            args["account_name"] = account_name
        if args.get("account_name") and (
            args.get("opening_balance") or args.get("opening_balance_date")
        ):
            return ToolCall(tool="update_account", arguments=args)

    if any(h in lower for h in CORRECTION_HINTS):
        if wants_transfer_correction(message):
            data = detect_transfer(message) or {}
            args: dict = {}
            if amount:
                args["amount"] = amount
            if data.get("from_account_name"):
                args["from_account_name"] = data["from_account_name"]
            if data.get("to_account_name"):
                args["to_account_name"] = data["to_account_name"]
            if args:
                return ToolCall(tool="update_transfer", arguments=args)
        args: dict = {}
        if amount:
            args["amount"] = amount
        period = None
        if "fatura" in lower:
            from app.services.credit_cards import parse_invoice_period_hint

            period = parse_invoice_period_hint(message)
            if period:
                args["invoice_due_month"], args["invoice_due_year"] = period
        desc_update = UPDATE_DESCRIPTION_RE.search(message)
        if desc_update:
            new_desc = (desc_update.group(1) or desc_update.group(2) or "").strip(" .,")
            if period:
                new_desc = re.sub(
                    r"\s*(?:na|para\s+a|da)?\s*fatura\s+(?:de\s+)?[\w/.-]+$",
                    "",
                    new_desc,
                    flags=re.IGNORECASE,
                ).strip(" .,")
            if len(new_desc) >= 2:
                args["description"] = correct_movement_description(new_desc)[:255]
        if "description" not in args:
            for keyword in ("passagem", "passagens", "mercado", "transporte"):
                if keyword in lower:
                    args["description"] = keyword
                    break
        for account_hint in ("mercado pago", "carteira", "nubank", "itau", "itaú", "bradesco"):
            if account_hint in lower:
                args["account_name"] = account_hint.title() if account_hint != "mercado pago" else "Mercado Pago"
                break
        if args:
            return ToolCall(tool="update_transaction", arguments=args)
        return None

    if wants_list_accounts(message):
        return ToolCall(tool="list_accounts", arguments={})

    from app.services.intents import wants_list_invoices, wants_pay_invoice, detect_invoice_query, detect_pay_invoice

    if wants_pay_invoice(message):
        data = detect_pay_invoice(message) or {}
        return ToolCall(tool="pay_invoice", arguments=data)

    if wants_list_invoices(message):
        data = detect_invoice_query(message) or {}
        return ToolCall(tool="list_invoices", arguments=data)

    if wants_pay_invoice(message):
        data = detect_pay_invoice(message) or {}
        return ToolCall(tool="pay_invoice", arguments=data)

    if wants_list_categories(message):
        return ToolCall(tool="list_categories", arguments={})

    if wants_category_creation(message):
        data = detect_category_creation(message) or {}
        args: dict = {}
        if data.get("name"):
            args["name"] = data["name"]
        if data.get("type"):
            args["type"] = data["type"]
        if data.get("keywords"):
            args["keywords"] = data["keywords"]
        if not args.get("name"):
            args["name"] = ""
        if not args.get("type"):
            args["type"] = "expense"
        return ToolCall(tool="create_category", arguments=args)

    from app.services.intents import wants_card_creation, detect_card_creation

    if wants_card_creation(message):
        data = detect_card_creation(message) or {}
        args: dict = {}
        for key in (
            "name",
            "institution",
            "closing_day",
            "due_day",
            "credit_limit",
            "settlement_account_name",
        ):
            if data.get(key) is not None:
                args[key] = data[key]
        if not args.get("name"):
            args["name"] = ""
        return ToolCall(tool="create_card", arguments=args)

    if any(h in lower for h in BUDGET_HINTS):
        return ToolCall(tool="get_budget_status", arguments={})

    if any(h in lower for h in SUMMARY_HINTS):
        return ToolCall(tool="get_summary", arguments={})

    if amount and wants_transfer(message):
        data = detect_transfer(message) or {}
        args: dict = {"amount": amount}
        if data.get("from_account_name"):
            args["from_account_name"] = data["from_account_name"]
        if data.get("to_account_name"):
            args["to_account_name"] = data["to_account_name"]
        tx_date = parse_date(lower)
        if tx_date:
            args["transaction_date"] = tx_date.isoformat()
        return ToolCall(tool="register_transfer", arguments=args)

    if wants_realize_planned(message):
        args: dict = {}
        if amount:
            args["amount"] = amount
        for keyword in ("passagem", "passagens", "mercado", "transporte", "salário", "salario"):
            if keyword in lower:
                args["description"] = keyword
                break
        return ToolCall(tool="realize_planned", arguments=args)

    if wants_planned_movement(message):
        planned = detect_planned_movement(message)
        tool = (
            "register_income"
            if planned.get("tx_type") == "income"
            else "register_expense"
        )
        args: dict = {}
        if amount:
            args["amount"] = amount
            args["description"] = extract_description(message, amount)
            tx_date = parse_date(lower)
            if tx_date:
                args["transaction_date"] = tx_date.isoformat()
        return ToolCall(tool=tool, arguments=args)

    if wants_register_expense(message):
        return ToolCall(tool="register_expense", arguments={})

    if wants_register_income(message):
        return ToolCall(tool="register_income", arguments={})

    if any(h in lower for h in LIST_HINTS):
        tx_type = "expense" if "despesa" in lower or "gasto" in lower else "all"
        return ToolCall(tool="list_transactions", arguments={"limit": 10, "type": tx_type})

    if amount and any(h in lower for h in EXPENSE_HINTS):
        return ToolCall(
            tool="register_expense",
            arguments={
                "amount": amount,
                "description": extract_description(message, amount),
                "transaction_date": (parse_date(lower) or local_today()).isoformat(),
            },
        )

    if amount and any(h in lower for h in INCOME_HINTS):
        return ToolCall(
            tool="register_income",
            arguments={
                "amount": amount,
                "description": extract_description(message, amount),
                "transaction_date": (parse_date(lower) or local_today()).isoformat(),
            },
        )

    return None


def correct_tool_call_descriptions(tool_call: ToolCall) -> ToolCall:
    args = dict(tool_call.arguments)
    changed = False
    if tool_call.tool in DESCRIPTION_TOOLS:
        description = args.get("description")
        if isinstance(description, str) and description.strip():
            args["description"] = correct_movement_description(description)
            changed = True
    if tool_call.tool == "create_category":
        name = args.get("name")
        if isinstance(name, str) and name.strip():
            corrected = correct_category_name(name)
            if corrected != name:
                args["name"] = corrected
                changed = True
    if not changed:
        return tool_call
    return ToolCall(tool=tool_call.tool, arguments=args)


def execute_tool(db, user_id: int, tool_call: ToolCall) -> dict:
    tool_call = correct_tool_call_descriptions(tool_call)
    tool = tool_call.tool
    args = tool_call.arguments

    if tool == "register_expense":
        payload = RegisterExpenseInput(**args)
        return {
            "action": "register_expense",
            "result": finance.register_expense(db, user_id, payload),
        }
    if tool == "register_income":
        payload = RegisterIncomeInput(**args)
        return {
            "action": "register_income",
            "result": finance.register_income(db, user_id, payload),
        }
    if tool == "register_transfer":
        payload = RegisterTransferInput(**args)
        return {
            "action": "register_transfer",
            "result": finance.register_transfer(db, user_id, payload),
        }
    if tool == "realize_planned":
        payload = RealizePlannedInput(**args)
        return {
            "action": "realize_planned",
            "result": finance.realize_planned(db, user_id, payload),
        }
    if tool == "update_transfer":
        payload = UpdateTransferInput(**args)
        return {
            "action": "update_transfer",
            "result": finance.update_transfer(db, user_id, payload),
        }
    if tool == "update_transaction":
        payload = UpdateTransactionInput(**args)
        return {
            "action": "update_transaction",
            "result": finance.update_transaction(db, user_id, payload),
        }
    if tool == "update_account":
        payload = UpdateAccountInput(**args)
        return {
            "action": "update_account",
            "result": finance.update_account(db, user_id, payload),
        }
    if tool == "update_card":
        payload = UpdateCardInput(**args)
        return {
            "action": "update_card",
            "result": finance.update_card(db, user_id, payload),
        }
    if tool == "delete_card":
        payload = DeleteCardInput(**args)
        return {
            "action": "delete_card",
            "result": finance.deactivate_card(db, user_id, payload),
        }
    if tool == "delete_transaction":
        clean_args = {k: v for k, v in args.items() if not str(k).startswith("_")}
        payload = DeleteTransactionInput(**clean_args)
        return {
            "action": "delete_transaction",
            "result": finance.delete_transaction(db, user_id, payload),
        }
    if tool == "list_transactions":
        payload = ListTransactionsInput(**args)
        return {
            "action": "list_transactions",
            "result": finance.list_transactions(db, user_id, payload),
        }
    if tool == "list_accounts":
        from app.services.credit_cards import list_credit_cards

        return {
            "action": "list_accounts",
            "result": {
                "accounts": finance.account_balances(db, user_id),
                "cards": list_credit_cards(db, user_id),
            },
        }
    if tool == "list_categories":
        return {
            "action": "list_categories",
            "result": finance.list_user_categories(db, user_id),
        }
    if tool == "get_summary":
        payload = SummaryInput(**args)
        return {"action": "get_summary", "result": finance.get_summary(db, user_id, payload)}
    if tool == "get_budget_status":
        payload = BudgetStatusInput(**args)
        return {
            "action": "get_budget_status",
            "result": finance.get_budget_status(db, user_id, payload),
        }
    if tool == "categorize":
        category = finance.categorize_by_keywords(
            db, user_id, args["description"], args.get("type", "expense")
        )
        return {
            "action": "categorize",
            "result": {"category": category.name if category else None},
        }
    if tool == "create_account":
        payload = CreateAccountInput(**args)
        return {
            "action": "create_account",
            "result": finance.create_account(db, user_id, payload),
        }
    if tool == "create_card":
        payload = CreateCardInput(**args)
        return {
            "action": "create_card",
            "result": finance.create_card(db, user_id, payload),
        }
    if tool == "create_category":
        payload = CreateCategoryInput(**args)
        return {
            "action": "create_category",
            "result": finance.create_category(db, user_id, payload),
        }
    if tool == "list_invoices":
        from app.services.credit_cards import list_invoices

        return {
            "action": "list_invoices",
            "result": list_invoices(
                db,
                user_id,
                account_name=args.get("account_name"),
                limit=args.get("limit", 12),
            ),
        }
    if tool == "pay_invoice":
        from app.services.credit_cards import pay_invoice

        payload = PayInvoiceInput(**args)
        pay_date = payload.payment_date
        if isinstance(pay_date, str):
            pay_date = date.fromisoformat(pay_date)
        return {
            "action": "pay_invoice",
            "result": pay_invoice(
                db,
                user_id,
                invoice_id=payload.invoice_id,
                account_name=payload.account_name,
                from_account_name=payload.from_account_name,
                payment_date=pay_date,
                due_month=payload.due_month,
                due_year=payload.due_year,
            ),
        }
    raise ValueError(f"Ferramenta desconhecida: {tool}")


def format_tool_result(action: str, result) -> str:
    if action in {"register_expense", "register_income"}:
        tx = result
        verb = "Despesa" if action == "register_expense" else "Receita"
        if tx.get("status") == "planned":
            verb = f"Previsão de {verb.lower()}"
        account_part = ""
        if tx.get("card"):
            account_part = f" no cartão {tx.get('card')}"
            if tx.get("invoice_label"):
                account_part += f" ({tx.get('invoice_label')})"
        elif tx.get("account"):
            account_part = f" na conta {tx.get('account')}"
        return (
            f"{verb} de R$ {tx['amount']} em '{tx['description']}' "
            f"({tx.get('category') or 'sem categoria'}) registrada{account_part} "
            f"em {tx['transaction_date']}."
        )
    if action == "realize_planned":
        planned = result["planned"]
        actual = result["actual"]
        account_part = f" na conta {actual['account']}" if actual.get("account") else ""
        return (
            f"Previsto realizado: '{planned['description']}' — "
            f"previsto R$ {planned['amount']} em {planned['transaction_date']}, "
            f"realizado R$ {actual['amount']} em {actual['transaction_date']}{account_part}."
        )
    if action == "update_transaction":
        tx = result
        where = ""
        if tx.get("card"):
            where = f"cartão {tx['card']}"
            if tx.get("invoice_label"):
                where += f" ({tx['invoice_label']})"
        elif tx.get("account"):
            where = f"conta {tx['account']}"
        else:
            where = "sem conta/cartão"
        msg = (
            f"Lançamento atualizado (id {tx['id']}): R$ {tx['amount']} em "
            f"'{tx['description']}' — {where}, "
            f"categoria {tx['category'] or 'sem categoria'}, data {tx['transaction_date']}."
        )
        if result.get("invoice_moved") and tx.get("invoice_label"):
            msg += f" Movido para {tx['invoice_label']}."
        return msg
    if action == "update_account":
        acc = result
        parts = [f"Conta '{acc['name']}' atualizada com sucesso."]
        if acc.get("institution"):
            parts.append(f"Instituição: {acc['institution']}.")
        parts.append(f"Saldo inicial: R$ {acc['opening_balance']}.")
        if acc.get("opening_balance_date_label"):
            parts.append(f"Data do saldo inicial: {acc['opening_balance_date_label']}.")
        return " ".join(parts)
    if action == "update_card":
        card = result
        parts = [f"Cartão '{card['name']}' atualizado com sucesso."]
        if card.get("institution"):
            parts.append(f"Instituição: {card['institution']}.")
        if card.get("closing_day"):
            parts.append(f"Fechamento dia {card['closing_day']}.")
        if card.get("due_day"):
            parts.append(f"Vencimento dia {card['due_day']}.")
        if card.get("credit_limit"):
            parts.append(f"Limite R$ {card['credit_limit']}.")
        if card.get("settlement_account_name"):
            parts.append(f"Conta de liquidação: {card['settlement_account_name']}.")
        return " ".join(parts)
    if action == "delete_card":
        card = result
        return f"Cartão '{card['name']}' excluído com sucesso."
    if action == "delete_transaction":
        if isinstance(result, dict) and result.get("deleted"):
            legs = result["deleted"]
            return (
                f"Transferência excluída ({len(legs)} lançamentos): "
                f"R$ {legs[0]['amount']} — {legs[0].get('description', '')}."
            )
        tx = result
        return (
            f"Lançamento excluído: R$ {tx['amount']} em '{tx['description']}' "
            f"({tx['account']}, {tx['transaction_date']})."
        )
    if action == "list_transactions":
        if not result:
            return "Nenhuma transação encontrada."
        lines = [
            f"- {tx['transaction_date']}: {tx.get('type_label', tx['type'])} R$ {tx['amount']} — {tx['description']}"
            for tx in result
        ]
        return "Últimas transações:\n" + "\n".join(lines)
    if action == "list_accounts":
        accounts = result.get("accounts", result) if isinstance(result, dict) else result
        cards = result.get("cards", []) if isinstance(result, dict) else []
        lines = []
        if not accounts and not cards:
            return "Nenhuma conta cadastrada."
        for acc in accounts:
            line = f"- {acc['account']} ({acc['account_type_label']})"
            if acc.get("institution"):
                line += f" — {acc['institution']}"
            line += f" — saldo R$ {acc['balance']}"
            lines.append(line)
        for card in cards:
            line = f"- {card['name']} (Cartão)"
            if card.get("institution"):
                line += f" — {card['institution']}"
            if card.get("current_invoice_total"):
                line += f" — fatura R$ {card['current_invoice_total']}"
                if card.get("current_invoice_due_label"):
                    line += f" (vence {card['current_invoice_due_label']})"
            if card.get("available_limit"):
                line += f" — disponível R$ {card['available_limit']}"
            lines.append(line)
        return "Suas contas e cartões:\n" + "\n".join(lines)
    if action == "list_invoices":
        if not result:
            return "Nenhuma fatura encontrada."
        lines = [
            f"- {inv['account_name']}: R$ {inv['total']} — vence {inv['due_date_label']} ({inv['status_label']})"
            for inv in result
        ]
        return "Faturas:\n" + "\n".join(lines)
    if action == "list_categories":
        if not result:
            return "Nenhuma categoria cadastrada."
        lines = [f"- {cat['name']} ({cat['type_label']})" for cat in result]
        return "Suas categorias:\n" + "\n".join(lines)
    if action == "get_summary":
        text = (
            f"Resumo ({result.get('period_label', '')}): "
            f"receitas R$ {result['income']}, despesas R$ {result['expense']}, "
            f"resultado do período R$ {result['balance']}, "
            f"saldo anterior R$ {result.get('previous_balance', '0')}, "
            f"resultado final R$ {result.get('ending_balance', result['balance'])}, "
            f"saldo total R$ {result['total_balance']}."
        )
        invoices = result.get("card_invoices") or {}
        cards = invoices.get("cards") or []
        if cards:
            text += (
                f" Faturas em aberto: R$ {invoices.get('unpaid_total', '0')}"
                f" ({invoices.get('unpaid_count', 0)} cartão(ões))."
            )
            for card in cards:
                if not card.get("current_invoice_id"):
                    continue
                line = (
                    f" {card['name']}: R$ {card.get('current_invoice_total', '0')}"
                    f" vence {card.get('current_invoice_due_label', '')}"
                    f" ({card.get('current_invoice_status_label', '')})."
                )
                if card.get("available_limit"):
                    line += f" Disponível R$ {card['available_limit']}."
                text += line
        return text
    if action == "get_budget_status":
        if not result:
            return "Nenhum orçamento definido para este período."
        lines = [
            f"- {b['category']}: R$ {b['spent']} / R$ {b['limit']} ({b['percent_used']}%)"
            for b in result
        ]
        return "Status dos orçamentos:\n" + "\n".join(lines)
    if action == "categorize":
        return f"Categoria sugerida: {result['category'] or 'Outros'}."
    if action == "create_card":
        card = result
        parts = [f"Cartão '{card['name']}' cadastrado com sucesso."]
        if card.get("institution"):
            parts.append(f"Instituição: {card['institution']}.")
        if card.get("closing_day"):
            parts.append(f"Fechamento dia {card['closing_day']}.")
        if card.get("due_day"):
            parts.append(f"Vencimento dia {card['due_day']}.")
        if card.get("credit_limit"):
            parts.append(f"Limite R$ {card['credit_limit']}.")
        if card.get("settlement_account_name"):
            parts.append(f"Conta de liquidação: {card['settlement_account_name']}.")
        return " ".join(parts)
    if action == "create_account":
        acc = result
        parts = [f"Conta '{acc['name']}' ({acc['account_type_label']}) cadastrada com sucesso."]
        if acc.get("institution"):
            parts.append(f"Instituição: {acc['institution']}.")
        parts.append(f"Saldo inicial: R$ {acc['opening_balance']}.")
        if acc.get("opening_balance_date_label"):
            parts.append(f"Data do saldo inicial: {acc['opening_balance_date_label']}.")
        return " ".join(parts)
    if action == "create_category":
        cat = result
        parts = [f"Categoria '{cat['name']}' ({cat['type_label']}) cadastrada com sucesso."]
        if cat.get("keywords"):
            parts.append(f"Palavras-chave: {cat['keywords']}.")
        return " ".join(parts)
    if action == "update_transfer":
        tx = result
        return (
            f"Transferência atualizada: R$ {tx['amount']} de {tx['from_account']} "
            f"para {tx['to_account']} em {tx['transaction_date']}."
        )
    if action == "register_transfer":
        tx = result
        return (
            f"Transferência de R$ {tx['amount']} de {tx['from_account']} "
            f"para {tx['to_account']} em {tx['transaction_date']}."
        )
    if action == "pay_invoice":
        inv = result["invoice"]
        payment = result.get("payment") or {}
        settled = int(result.get("settled_count") or 0)
        lines = [
            f"Fatura paga: {inv['total']} do cartão {inv.get('account_name', '')} "
            f"(vencimento {inv['due_date_label']}).",
        ]
        if payment.get("account"):
            lines.append(f"Débito na conta {payment['account']}.")
        if settled:
            lines.append(
                f"{settled} lançamento(s) previsto(s) da fatura foram liquidados."
            )
        return " ".join(lines)
    return json.dumps(result, ensure_ascii=False)


def format_pending_confirmation(tool_call) -> str:
    tool_call = correct_tool_call_descriptions(tool_call)
    args = tool_call.arguments

    def _format_dates(status: str) -> str:
        if args.get("installment_count"):
            lines: list[str] = []
            if args.get("competence_date"):
                lines.append(f"Competência: {args.get('competence_date')}")
            if args.get("due_date"):
                lines.append(f"Vencimento: {args.get('due_date')}")
            if status != "planned":
                payment = args.get("payment_date") or args.get("transaction_date")
                if payment:
                    lines.append(f"Data da realização: {payment}")
            return "\n".join(lines) + ("\n" if lines else "")
        if status == "planned":
            comp = args.get("competence_date") or args.get("transaction_date") or "hoje"
            due = args.get("due_date") or args.get("transaction_date") or "hoje"
            return f"Competência: {comp}\nVencimento: {due}"
        payment = args.get("payment_date") or args.get("transaction_date") or "hoje"
        return f"Data da realização: {payment}"

    def _format_recurrence() -> str:
        freq = args.get("frequency")
        if not freq:
            return ""
        from app.services.recurrence import FREQUENCY_LABELS

        label = FREQUENCY_LABELS.get(freq, freq)
        end = args.get("recurrence_end_date")
        if end:
            return f"Lançamento fixo ({label}) até {end}\n"
        return f"Lançamento fixo ({label})\n"

    def _format_installments() -> str:
        count = args.get("installment_count")
        interval = args.get("installment_interval")
        if not count:
            return ""
        from app.schemas import decimal_to_cents, format_brl
        from app.services.installments import INTERVAL_LABELS, split_cents

        label = INTERVAL_LABELS.get(interval or "", interval or "")
        basis = args.get("installment_amount_basis") or "total"
        start_idx = int(args.get("installment_start_index") or 1)
        amount_str = str(args.get("amount") or "0")
        amount_cents = decimal_to_cents(amount_str)
        range_note = ""
        if start_idx > 1:
            range_note = f" (a partir da parcela {start_idx}/{count})"
        if basis == "installment":
            total_cents = amount_cents * count
            return (
                f"Parcelado: {count}x {label}{range_note} — R$ {amount_str} cada "
                f"(total R$ {format_brl(total_cents)})\n"
            )
        per_cents = split_cents(amount_cents, count)[0]
        return (
            f"Parcelado: {count}x {label}{range_note} — total R$ {amount_str} "
            f"(cerca de R$ {format_brl(per_cents)} cada)\n"
        )

    if tool_call.tool == "register_expense":
        kind = "previsão de despesa" if args.get("status") == "planned" else "despesa"
        if args.get("card_name"):
            target = f"Cartão: {args.get('card_name')}\n"
            if args.get("due_date"):
                try:
                    due = date.fromisoformat(str(args["due_date"]))
                    target += f"Fatura prevista: Fatura · {due.strftime('%d/%m')}\n"
                except ValueError:
                    pass
        else:
            target = f"Conta: {args.get('account_name')}\n"
        return (
            f"Confirmar {kind} de R$ {args.get('amount')} em "
            f"'{args.get('description')}'?\n"
            f"{target}"
            f"Categoria: {args.get('category_name')}\n"
            f"{_format_dates(args.get('status', 'actual'))}\n"
            f"{_format_recurrence()}"
            f"{_format_installments()}"
            f"Clique em Confirmar para registrar."
        )
    if tool_call.tool == "register_income":
        kind = "previsão de receita" if args.get("status") == "planned" else "receita"
        if args.get("card_name"):
            target = f"Cartão: {args.get('card_name')}\n"
            if args.get("due_date"):
                try:
                    due = date.fromisoformat(str(args["due_date"]))
                    target += f"Fatura prevista: Fatura · {due.strftime('%d/%m')}\n"
                except ValueError:
                    pass
        else:
            target = f"Conta: {args.get('account_name')}\n"
        return (
            f"Confirmar {kind} de R$ {args.get('amount')} em "
            f"'{args.get('description')}'?\n"
            f"{target}"
            f"Categoria: {args.get('category_name')}\n"
            f"{_format_dates(args.get('status', 'actual'))}\n"
            f"{_format_recurrence()}"
            f"{_format_installments()}"
            f"Clique em Confirmar para registrar."
        )
    if tool_call.tool == "realize_planned":
        lines = ["Confirmar realização do lançamento previsto?"]
        if args.get("planned_id"):
            lines.append(f"ID previsto: {args.get('planned_id')}")
        if args.get("description"):
            lines.append(f"Descrição: {args.get('description')}")
        if args.get("amount"):
            lines.append(f"Valor realizado: R$ {args.get('amount')}")
        if args.get("account_name"):
            lines.append(f"Conta: {args.get('account_name')}")
        payment = args.get("payment_date") or args.get("transaction_date") or "hoje"
        lines.append(f"Data de pagamento: {payment}")
        if args.get("competence_date"):
            lines.append(f"Competência: {args.get('competence_date')}")
        if args.get("due_date"):
            lines.append(f"Vencimento: {args.get('due_date')}")
        lines.append("Clique em Confirmar para registrar o realizado.")
        return "\n".join(lines)
    if tool_call.tool == "update_transfer":
        lines = ["Confirmar correção da transferência:"]
        if args.get("amount"):
            lines.append(f"Valor: R$ {args.get('amount')}.")
        if args.get("from_account_name"):
            lines.append(f"De: {args.get('from_account_name')}.")
        if args.get("to_account_name"):
            lines.append(f"Para: {args.get('to_account_name')}.")
        if args.get("transaction_date"):
            lines.append(f"Data: {args.get('transaction_date')}.")
        lines.append("Clique em Confirmar para salvar as alterações.")
        return " ".join(lines)
    if tool_call.tool == "register_transfer":
        return (
            f"Confirmar transferência de R$ {args.get('amount')} "
            f"de {args.get('from_account_name')} para {args.get('to_account_name')}?\n"
            f"Data: {args.get('transaction_date') or 'hoje'}\n"
            f"Clique em Confirmar para registrar."
        )
    if tool_call.tool == "pay_invoice":
        lines = ["Confirmar pagamento da fatura?"]
        if args.get("invoice_total"):
            lines.append(f"Valor: {args.get('invoice_total')}.")
        if args.get("invoice_due_label"):
            lines.append(f"Vencimento: {args.get('invoice_due_label')}.")
        lines.append(
            f"Cartão: {args.get('account_name') or 'fatura #' + str(args.get('invoice_id', ''))}"
        )
        lines.append(f"Conta de débito: {args.get('from_account_name')}")
        lines.append(f"Data: {args.get('payment_date') or 'hoje'}")
        lines.append("Os lançamentos previstos desta fatura serão liquidados automaticamente.")
        lines.append("Clique em Confirmar para registrar.")
        return "\n".join(lines)
    if tool_call.tool == "create_card":
        lines = [
            f"Confirmar cadastro do cartão '{args.get('name')}'?"
        ]
        if args.get("institution"):
            lines.append(f"Instituição: {args.get('institution')}.")
        lines.append(f"Fechamento: dia {args.get('closing_day')}.")
        lines.append(f"Vencimento: dia {args.get('due_day')}.")
        lines.append(f"Conta de liquidação: {args.get('settlement_account_name')}.")
        if args.get("credit_limit"):
            lines.append(f"Limite: R$ {args.get('credit_limit')}.")
        lines.append("Clique em Confirmar para cadastrar.")
        return " ".join(lines)
    if tool_call.tool == "create_account":
        from app.services.account_wizard import TYPE_LABELS

        lines = [
            f"Confirmar cadastro da conta '{args.get('name')}' "
            f"({TYPE_LABELS.get(args.get('account_type'), args.get('account_type'))})?"
        ]
        if args.get("institution"):
            lines.append(f"Instituição: {args.get('institution')}.")
        balance = args.get("opening_balance")
        lines.append(f"Saldo inicial: R$ {balance if balance else '0,00'}.")
        if args.get("opening_balance_date"):
            lines.append(f"Data do saldo inicial: {args.get('opening_balance_date')}.")
        lines.append("Clique em Confirmar para cadastrar.")
        return " ".join(lines)
    if tool_call.tool == "create_category":
        from app.services.category_wizard import TYPE_LABELS

        type_label = TYPE_LABELS.get(args.get("type"), args.get("type"))
        lines = [
            f"Confirmar cadastro da categoria '{args.get('name')}' ({type_label})?"
        ]
        if args.get("keywords"):
            lines.append(f"Palavras-chave: {args.get('keywords')}.")
        lines.append("Clique em Confirmar para cadastrar.")
        return " ".join(lines)
    if tool_call.tool == "update_transaction":
        parts = ["Confirmar atualização do lançamento:"]
        if args.get("transaction_id"):
            parts.append(f"ID: {args.get('transaction_id')}.")
        if args.get("description"):
            parts.append(f"Descrição: {args.get('description')}.")
        if args.get("amount"):
            parts.append(f"Valor: R$ {args.get('amount')}.")
        if args.get("account_name"):
            parts.append(f"Conta: {args.get('account_name')}.")
        if args.get("category_name"):
            parts.append(f"Categoria: {args.get('category_name')}.")
        if args.get("transaction_date"):
            parts.append(f"Data: {args.get('transaction_date')}.")
        if args.get("due_date"):
            parts.append(f"Vencimento: {args.get('due_date')}.")
        if args.get("competence_date"):
            parts.append(f"Competência: {args.get('competence_date')}.")
        if args.get("invoice_due_month") is not None:
            month = int(args["invoice_due_month"])
            year = args.get("invoice_due_year")
            label = f"{month:02d}"
            if year:
                label = f"{month:02d}/{year}"
            parts.append(f"Fatura destino: vencimento {label}.")
        parts.append("Clique em Confirmar para salvar as alterações.")
        return " ".join(parts)
    if tool_call.tool == "update_account":
        parts = ["Confirmar atualização da conta:"]
        if args.get("account_name"):
            parts.append(f"Conta: {args.get('account_name')}.")
        if args.get("name"):
            parts.append(f"Novo apelido: {args.get('name')}.")
        if args.get("institution"):
            parts.append(f"Instituição: {args.get('institution')}.")
        if args.get("account_type"):
            parts.append(f"Tipo: {args.get('account_type')}.")
        if args.get("opening_balance"):
            parts.append(f"Saldo inicial: R$ {args.get('opening_balance')}.")
        if args.get("opening_balance_date"):
            parts.append(f"Data do saldo inicial: {args.get('opening_balance_date')}.")
        parts.append("Clique em Confirmar para salvar as alterações.")
        return " ".join(parts)
    if tool_call.tool == "update_card":
        parts = ["Confirmar atualização do cartão:"]
        if args.get("card_name"):
            parts.append(f"Cartão: {args.get('card_name')}.")
        if args.get("name"):
            parts.append(f"Novo apelido: {args.get('name')}.")
        if args.get("institution"):
            parts.append(f"Instituição: {args.get('institution')}.")
        if args.get("closing_day"):
            parts.append(f"Fechamento: dia {args.get('closing_day')}.")
        if args.get("due_day"):
            parts.append(f"Vencimento: dia {args.get('due_day')}.")
        if args.get("credit_limit"):
            parts.append(f"Limite: R$ {args.get('credit_limit')}.")
        if args.get("settlement_account_name"):
            parts.append(f"Conta de liquidação: {args.get('settlement_account_name')}.")
        parts.append("Clique em Confirmar para salvar as alterações.")
        return " ".join(parts)
    if tool_call.tool == "delete_card":
        parts = ["Confirmar exclusão do cartão:"]
        if args.get("card_name"):
            parts.append(f"Cartão: {args.get('card_name')}.")
        elif args.get("card_id"):
            parts.append(f"ID: {args.get('card_id')}.")
        parts.append("Clique em Confirmar para excluir.")
        return " ".join(parts)
    if tool_call.tool == "delete_transaction":
        parts = ["Confirmar exclusão do lançamento:"]
        if args.get("transaction_id"):
            parts.append(f"ID: {args.get('transaction_id')}.")
        if args.get("description"):
            parts.append(f"Descrição: {args.get('description')}.")
        if args.get("amount"):
            parts.append(f"Valor: R$ {args.get('amount')}.")
        if args.get("_preview"):
            preview = args["_preview"]
            parts = [
                "Confirmar exclusão do lançamento:",
                f"R$ {preview.get('amount')} em '{preview.get('description')}'",
                f"— conta {preview.get('account')}, data {preview.get('transaction_date')}.",
            ]
        parts.append("Clique em Confirmar para excluir.")
        return " ".join(parts)
    return "Confirmar esta ação?"
