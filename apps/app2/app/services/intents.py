import re

from app.services.text_correction import correct_category_name

ACCOUNT_HINTS = (
    "cadastrar conta",
    "nova conta",
    "adicionar conta",
    "criar conta",
    "registrar conta",
)

ACCOUNT_CREATION_RE = re.compile(
    r"\b(?:cadastrar|cadastre|cadastra|criar|crie|cria|adicionar|adicione|adiciona|"
    r"registrar|registre|registra|nova)\b(?:\s+\w+){0,3}\s+conta\b",
    re.IGNORECASE,
)

LIST_ACCOUNT_RE = re.compile(
    r"\b(?:liste|listar|listem|mostre|mostrar|ver|quais)\b.*\bcontas?\b|"
    r"\bcontas?\s+banc[aá]ri",
    re.IGNORECASE,
)

LIST_ACCOUNT_PHRASES = (
    "minhas contas",
    "quais contas",
    "quais são as contas",
    "quais a conta",
    "quais as contas",
    "ver contas",
)

CATEGORY_HINTS = (
    "cadastrar categoria",
    "nova categoria",
    "adicionar categoria",
    "criar categoria",
    "registrar categoria",
)

LIST_CATEGORY_RE = re.compile(
    r"\b(?:liste|listar|listem|mostre|mostrar|ver|quais)\b.*\bcategor(?:ia|ias)\b|"
    r"\bcategor(?:ia|ias)\s+cadastrad",
    re.IGNORECASE,
)

LIST_CATEGORY_PHRASES = (
    "minhas categorias",
    "quais categorias",
    "quais são as categorias",
    "quais as categorias",
    "ver categorias",
)

CATEGORY_CREATION_RE = re.compile(
    r"\b(?:cadastrar|cadastre|cadastra|criar|crie|cria|adicionar|adicione|adiciona|"
    r"registrar|registre|registra|nova)\b(?:\s+\w+){0,4}\s+categor(?:ia|ias)\b",
    re.IGNORECASE,
)

CATEGORY_NAME_NOISE_RE = re.compile(
    r"\b(?:categoria|categorias|de|do|da|dos|das|uma|um|nova|novo|para|"
    r"despesa|despesas|receita|receitas|gasto|gastos)\b",
    re.IGNORECASE,
)

CATEGORY_EXPENSE_WORDS = ("despesa", "despesas", "gasto", "gastos", "debito", "débito")
CATEGORY_INCOME_WORDS = ("receita", "receitas", "entrada", "entradas", "credito", "crédito")


def wants_list_accounts(message: str) -> bool:
    lower = message.lower().strip()
    if ACCOUNT_CREATION_RE.search(lower):
        return False
    if any(hint in lower for hint in ACCOUNT_HINTS):
        return False
    if LIST_ACCOUNT_RE.search(lower):
        return True
    return any(phrase in lower for phrase in LIST_ACCOUNT_PHRASES)


def wants_account_creation(message: str) -> bool:
    if wants_list_accounts(message):
        return False
    lower = message.lower().strip()
    if any(hint in lower for hint in ACCOUNT_HINTS):
        return True
    return bool(ACCOUNT_CREATION_RE.search(lower))


def wants_list_categories(message: str) -> bool:
    lower = message.lower().strip()
    if CATEGORY_CREATION_RE.search(lower):
        return False
    if any(hint in lower for hint in CATEGORY_HINTS):
        return False
    if LIST_CATEGORY_RE.search(lower):
        return True
    return any(phrase in lower for phrase in LIST_CATEGORY_PHRASES)


def wants_category_creation(message: str) -> bool:
    if wants_list_categories(message):
        return False
    lower = message.lower().strip()
    if any(hint in lower for hint in CATEGORY_HINTS):
        return True
    return bool(CATEGORY_CREATION_RE.search(lower))


def _parse_category_type(text: str) -> str | None:
    lower = text.lower()
    has_expense = any(w in lower for w in CATEGORY_EXPENSE_WORDS)
    has_income = any(w in lower for w in CATEGORY_INCOME_WORDS)
    if has_expense and not has_income:
        return "expense"
    if has_income and not has_expense:
        return "income"
    if lower.strip() in {"despesa", "despesas", "1"}:
        return "expense"
    if lower.strip() in {"receita", "receitas", "2"}:
        return "income"
    return None


def _extract_category_name(text: str) -> str | None:
    match = CATEGORY_CREATION_RE.search(text)
    if not match:
        return None
    cleaned = text[match.end() :].strip()
    cleaned = CATEGORY_NAME_NOISE_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -,.")
    if len(cleaned) >= 2:
        return correct_category_name(cleaned)[:100]
    return None


def detect_category_creation(message: str) -> dict | None:
    if not CATEGORY_CREATION_RE.search(message):
        return None
    data: dict = {}
    name = _extract_category_name(message)
    if name:
        data["name"] = name
    category_type = _parse_category_type(message)
    if category_type:
        data["type"] = category_type
    keywords_match = re.search(
        r"\b(?:palavras?-chave|keywords?)\s*:?\s*(.+)$",
        message,
        re.IGNORECASE,
    )
    if keywords_match:
        data["keywords"] = keywords_match.group(1).strip()[:500]
    return data


TRANSFER_RE = re.compile(
    r"\b(?:transferir|transferência|transferencia|transferencia|mover|enviar)\b",
    re.IGNORECASE,
)

TRANSFER_FROM_TO_RE = re.compile(
    r"\b(?:da|de|do)\s+(.+?)\s+(?:para|pra|pro)\s+(.+?)(?:\.|$)",
    re.IGNORECASE,
)


def wants_transfer(message: str) -> bool:
    return bool(TRANSFER_RE.search(message))


REGISTER_EXPENSE_RE = re.compile(
    r"\b(?:lancar|lançar|lance|registrar|registre|cadastrar|cadastre|criar)\b"
    r"(?:\s+(?:uma?|um))?\s*(?:despesa|despesas|gasto|gastos)\b",
    re.IGNORECASE,
)

REGISTER_INCOME_RE = re.compile(
    r"\b(?:lancar|lançar|lance|registrar|registre|cadastrar|cadastre|criar)\b"
    r"(?:\s+(?:uma?|um))?\s*(?:receita|receitas|entrada|entradas|ganho|ganhos)\b",
    re.IGNORECASE,
)

LIST_TRANSACTION_CONTEXT = re.compile(
    r"\b(?:liste|listar|listem|mostre|mostrar|ver|quais|últimas|ultimas|extrato|"
    r"histórico|historico)\b",
    re.IGNORECASE,
)

SUMMARY_CONTEXT = re.compile(
    r"\b(?:resumo|balanço|balanco|quanto\s+(?:gastei|recebi)|orcamento|orçamento)\b",
    re.IGNORECASE,
)

EXPENSE_ONLY_WORDS = frozenset({"despesa", "despesas", "gasto", "gastos"})
INCOME_ONLY_WORDS = frozenset({"receita", "receitas", "entrada", "entradas", "ganho", "ganhos"})


def _is_list_or_summary_context(lower: str) -> bool:
    return bool(LIST_TRANSACTION_CONTEXT.search(lower) or SUMMARY_CONTEXT.search(lower))


PLANNED_MOVEMENT_RE = re.compile(
    r"\b(?:previs[aã]o|previsto|prevista|agendar|agendado|agendada|"
    r"vou\s+(?:gastar|pagar|receber|ganhar)|irei\s+(?:gastar|pagar|receber))\b",
    re.IGNORECASE,
)

REALIZE_PLANNED_RE = re.compile(
    r"\b(?:realizei|realizar|confirmar|confirmo|efetivar|efetivei)\b.*\b(?:previs[aã]o|previsto|prevista)\b|"
    r"\b(?:previs[aã]o|previsto|prevista)\b.*\b(?:realizei|realizar|confirmar|confirmo|efetivar|efetivei)\b",
    re.IGNORECASE,
)


def wants_realize_planned(message: str) -> bool:
    return bool(REALIZE_PLANNED_RE.search(message.lower().strip()))


def wants_planned_movement(message: str) -> bool:
    lower = message.lower().strip()
    if _is_list_or_summary_context(lower):
        return False
    if wants_transfer(message) or wants_realize_planned(message):
        return False
    return bool(PLANNED_MOVEMENT_RE.search(lower))


def detect_planned_movement(message: str) -> dict:
    lower = message.lower()
    data: dict = {}
    if any(w in lower for w in ("receita", "receber", "ganhar", "entrada")):
        data["tx_type"] = "income"
    elif any(w in lower for w in ("despesa", "gastar", "pagar", "gasto")):
        data["tx_type"] = "expense"
    return data


def wants_register_expense(message: str) -> bool:
    lower = message.lower().strip()
    if wants_planned_movement(message):
        return False
    if _is_list_or_summary_context(lower):
        return False
    if wants_list_categories(message) or wants_list_accounts(message):
        return False
    if wants_transfer(message) or wants_category_creation(message):
        return False
    if lower in EXPENSE_ONLY_WORDS:
        return True
    if REGISTER_EXPENSE_RE.search(lower):
        return True
    if len(lower.split()) <= 6 and "despesa" in lower and "receita" not in lower:
        if re.search(r"\b(?:quero|lancar|lançar|lance|registrar|registre)\b", lower):
            return True
    return False


def wants_register_income(message: str) -> bool:
    lower = message.lower().strip()
    if wants_planned_movement(message):
        return False
    if _is_list_or_summary_context(lower):
        return False
    if wants_list_categories(message) or wants_list_accounts(message):
        return False
    if wants_transfer(message) or wants_category_creation(message):
        return False
    if lower in INCOME_ONLY_WORDS:
        return True
    if REGISTER_INCOME_RE.search(lower):
        return True
    if len(lower.split()) <= 6 and "receita" in lower and "despesa" not in lower:
        if re.search(r"\b(?:quero|lancar|lançar|lance|registrar|registre)\b", lower):
            return True
    return False


def detect_transfer(message: str) -> dict | None:
    if not wants_transfer(message) and not TRANSFER_FROM_TO_RE.search(message):
        return None
    data: dict = {}
    match = TRANSFER_FROM_TO_RE.search(message)
    if match:
        from_raw = match.group(1).strip(" -,.")
        to_raw = match.group(2).strip(" -,.")
        if len(from_raw) >= 2:
            data["from_account_name"] = from_raw[:100]
        if len(to_raw) >= 2:
            data["to_account_name"] = to_raw[:100]
    return data
