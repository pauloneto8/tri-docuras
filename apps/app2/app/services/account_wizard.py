import re

from app.schemas import AgentResponse, CreateAccountInput, ToolCall
from app.services.agent_suggestions import for_account_wizard_field
from app.services.intents import wants_account_creation
from app.services.tools import parse_amount, parse_opening_balance_date
from app.services.wizard_slots import is_complex_message, is_short_slot_message

WIZARD_KEY = "account_wizard"
SKIP_WORDS = {"pular", "nao", "não", "nenhum", "nenhuma", "sem", "-", "skip"}
CANCEL_WORDS = {"cancelar", "desistir", "abortar", "sair"}

ACCOUNT_CREATION_RE = re.compile(
    r"\b(?:cadastrar|cadastre|cadastra|criar|crie|cria|adicionar|adicione|adiciona|"
    r"registrar|registre|registra|nova)\b(?:\s+\w+){0,3}\s+conta\b",
    re.IGNORECASE,
)

ACCOUNT_TYPE_KEYWORDS = {
    "poupanca": ("poupança", "poupanca"),
    "carteira": ("carteira",),
    "cartao": ("cartão", "cartao", "credito", "crédito"),
    "corrente": ("corrente",),
}

NAME_NOISE_RE = re.compile(
    r"\b(corrente|poupança|poupanca|carteira|cartão|cartao|credito|crédito|"
    r"com|saldo|inicial|de|do|da|um|uma|outra|outro|novo|nova|reais?|"
    r"bancária|bancaria|bancário|bancario|financeira|financeiro)\b",
    re.IGNORECASE,
)

SALDO_CLAUSE_RE = re.compile(
    r"\b(?:com\s+)?saldo\s+(?:de|inicial(?:\s+de)?)\b.*$",
    re.IGNORECASE,
)

MONEY_LIKE_RE = re.compile(
    r"^(?:r\$\s*)?(?:\d{1,3}(?:\.\d{3})*,\d{2}|\d+(?:[.,]\d{1,2})?)\s*(?:reais?)?$",
    re.IGNORECASE,
)

# Aliases mais longos primeiro para "banco do brasil" ganhar de "bb".
INSTITUTION_ALIASES = (
    ("banco do brasil", "Banco do Brasil"),
    ("caixa econômica federal", "Caixa Econômica"),
    ("caixa economica federal", "Caixa Econômica"),
    ("caixa econômica", "Caixa Econômica"),
    ("caixa economica", "Caixa Econômica"),
    ("nubank", "Nubank"),
    ("mercado pago", "Mercado Pago"),
    ("bradesco", "Bradesco"),
    ("santander", "Santander"),
    ("itau", "Itaú"),
    ("itaú", "Itaú"),
    ("inter", "Inter"),
    ("caixa", "Caixa Econômica"),
    ("c6", "C6"),
    ("bb", "Banco do Brasil"),
    ("bn", "Nubank"),
)

FIELD_ORDER = ("name", "account_type", "institution", "opening_balance")

QUESTIONS = {
    "name": "Qual o apelido da conta? (ex.: Nubank, Itaú Corrente)",
    "account_type": "Qual o tipo da conta? Opções: corrente, poupança, carteira ou cartão.",
    "institution": "Qual a instituição financeira? (opcional — responda 'pular' para ignorar)",
    "opening_balance": "Qual o saldo inicial? (opcional — responda 'pular' ou '0' para ignorar)",
    "opening_balance_date": "A partir de qual data esse saldo inicial vale? (ex.: hoje, 01/08/2026)",
}

TYPE_LABELS = {
    "corrente": "Corrente",
    "poupanca": "Poupança",
    "carteira": "Carteira",
    "cartao": "Cartão",
}


def is_skip(message: str) -> bool:
    return message.strip().lower() in SKIP_WORDS


def is_cancel(message: str) -> bool:
    return message.strip().lower() in CANCEL_WORDS


def get_wizard(session: dict) -> dict | None:
    return session.get(WIZARD_KEY)


def clear_wizard(session: dict) -> None:
    session.pop(WIZARD_KEY, None)


def start_wizard(session: dict, initial: dict | None = None) -> None:
    data = {
        "name": None,
        "institution": None,
        "account_type": None,
        "opening_balance": None,
        "opening_balance_date": None,
        "institution_asked": False,
        "opening_balance_asked": False,
        "opening_balance_date_asked": False,
    }
    if initial:
        for key in ("name", "institution", "account_type", "opening_balance", "opening_balance_date"):
            if initial.get(key):
                data[key] = initial[key]
        if initial.get("institution"):
            data["institution_asked"] = True
        if initial.get("opening_balance") is not None:
            data["opening_balance_asked"] = True
        if initial.get("opening_balance_date"):
            data["opening_balance_date_asked"] = True
    session[WIZARD_KEY] = data


def _has_positive_opening_balance(wizard: dict) -> bool:
    balance = wizard.get("opening_balance")
    if not balance:
        return False
    try:
        from app.schemas import decimal_to_cents

        return decimal_to_cents(balance) > 0
    except (ValueError, Exception):
        return False


def parse_account_type(text: str) -> str | None:
    lower = text.lower()
    for account_type, keywords in ACCOUNT_TYPE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return account_type
    return None


def looks_like_amount(text: str) -> bool:
    value = text.strip()
    if not value:
        return False
    if parse_amount(value):
        return True
    if MONEY_LIKE_RE.match(value):
        return True
    lowered = value.lower()
    if "real" in lowered:
        without_unit = re.sub(r"\breais?\b", "", lowered, flags=re.IGNORECASE)
        without_unit = re.sub(r"r\$\s*", "", without_unit).strip()
        if not without_unit or parse_amount(without_unit):
            return True
    return False


def _strip_balance_clause(text: str) -> str:
    return SALDO_CLAUSE_RE.sub("", text).strip(" -,.")


def _institution_as_default_name(institution: str) -> bool:
    cleaned = institution.strip()
    return " " not in cleaned or len(cleaned) <= 10


def resolve_account_name(name: str | None, institution: str | None) -> str | None:
    if name and looks_like_amount(name):
        name = None
    if name and institution and name.lower() == institution.lower():
        if " " in name.strip() or len(name.strip()) > 8:
            name = None
    if not name and institution and _institution_as_default_name(institution):
        name = institution
    return name


def extract_account_name(message: str) -> str | None:
    text = message.strip()
    lower = text.lower()
    remainder = text
    match = ACCOUNT_CREATION_RE.search(lower)
    if match:
        idx = match.end()
        remainder = text[idx:].strip(" :,-")
    else:
        for hint in ACCOUNT_HINTS:
            if hint in lower:
                idx = lower.index(hint) + len(hint)
                remainder = text[idx:].strip(" :,-")
                break

    original_remainder = _strip_balance_clause(remainder)
    remainder = original_remainder
    for alias, _label in INSTITUTION_ALIASES:
        remainder = re.sub(re.escape(alias), " ", remainder, flags=re.IGNORECASE)

    remainder = NAME_NOISE_RE.sub(" ", remainder)
    amount = parse_amount(remainder)
    if amount:
        remainder = re.sub(re.escape(amount), "", remainder, flags=re.IGNORECASE)
        remainder = re.sub(r"r\$\s*", "", remainder, flags=re.IGNORECASE)
    remainder = re.sub(r"\s+", " ", remainder).strip(" -,.")
    if remainder and len(remainder) >= 2 and not looks_like_amount(remainder):
        return remainder[:100]

    institution = extract_institution(original_remainder) or extract_institution(message)
    if institution and _institution_as_default_name(institution):
        return institution[:100]
    return None


def extract_institution(message: str) -> str | None:
    lower = message.lower()
    for alias, label in INSTITUTION_ALIASES:
        if " " in alias or len(alias) > 3:
            if alias in lower:
                return label
        elif re.search(rf"\b{re.escape(alias)}\b", lower):
            return label
    return None


def detect_account_creation(message: str) -> dict | None:
    if not wants_account_creation(message):
        return None
    lower = message.lower().strip()
    data: dict = {}
    account_type = parse_account_type(lower)
    if account_type:
        data["account_type"] = account_type
    amount = parse_amount(lower)
    if amount:
        data["opening_balance"] = amount
    name = extract_account_name(message)
    institution = extract_institution(message)
    if institution:
        data["institution"] = institution
    name = resolve_account_name(name, institution)
    if name:
        data["name"] = name
    return data


def _sanitize_wizard_name(wizard: dict) -> None:
    name = wizard.get("name")
    institution = wizard.get("institution")
    if name and looks_like_amount(name):
        wizard["name"] = None
        name = None

    # Durante o wizard, apelido e instituição podem ser iguais (ex.: Mercado Pago).
    if wizard.get("institution_asked"):
        return

    if name and institution and name.lower() == institution.lower():
        if " " in name.strip() or len(name.strip()) > 8:
            wizard["name"] = None
            name = None
    resolved = resolve_account_name(wizard.get("name"), institution)
    wizard["name"] = resolved


def _next_field(wizard: dict) -> str | None:
    if not wizard.get("name"):
        return "name"
    if not wizard.get("account_type"):
        return "account_type"
    if not wizard.get("institution_asked"):
        return "institution"
    if not wizard.get("opening_balance_asked"):
        return "opening_balance"
    if _has_positive_opening_balance(wizard) and not wizard.get("opening_balance_date_asked"):
        return "opening_balance_date"
    return None


def _fill_field(wizard: dict, field: str, message: str) -> str | None:
    if field == "name":
        value = message.strip()
        if len(value) < 2:
            return "Informe um apelido com pelo menos 2 caracteres."
        if looks_like_amount(value):
            return "Apelido inválido. Informe um nome para a conta, não um valor monetário."
        wizard["name"] = value[:100]
        return None

    if field == "account_type":
        account_type = parse_account_type(message)
        if not account_type:
            return "Tipo inválido. Use: corrente, poupança, carteira ou cartão."
        wizard["account_type"] = account_type
        return None

    if field == "institution":
        wizard["institution_asked"] = True
        if is_skip(message):
            wizard["institution"] = None
        else:
            wizard["institution"] = message.strip()[:100]
        return None

    if field == "opening_balance":
        wizard["opening_balance_asked"] = True
        if is_skip(message):
            wizard["opening_balance"] = None
            wizard["opening_balance_date_asked"] = True
        else:
            amount = parse_amount(message) or message.strip()
            try:
                from app.schemas import decimal_to_cents

                cents = decimal_to_cents(amount)
                if cents <= 0:
                    wizard["opening_balance"] = None
                    wizard["opening_balance_date_asked"] = True
                else:
                    wizard["opening_balance"] = amount
            except (ValueError, Exception):
                return "Valor inválido. Informe um saldo como '500' ou '1.250,00', ou responda 'pular'."
        return None

    if field == "opening_balance_date":
        wizard["opening_balance_date_asked"] = True
        parsed = parse_opening_balance_date(message)
        if not parsed:
            return (
                "Data inválida. Informe quando o saldo inicial passa a valer "
                "(ex.: hoje, ontem, 01/08/2026)."
            )
        wizard["opening_balance_date"] = parsed
        return None

    return "Campo desconhecido."


def _wizard_summary(wizard: dict) -> str:
    lines = [
        f"Apelido: {wizard['name']}",
        f"Tipo: {TYPE_LABELS.get(wizard['account_type'], wizard['account_type'])}",
    ]
    if wizard.get("institution"):
        lines.append(f"Instituição: {wizard['institution']}")
    balance = wizard.get("opening_balance")
    if balance:
        lines.append(f"Saldo inicial: R$ {balance}")
        balance_date = wizard.get("opening_balance_date")
        if balance_date:
            from datetime import date

            lines.append(
                f"Data do saldo inicial: {date.fromisoformat(balance_date).strftime('%d/%m/%Y')}"
            )
    else:
        lines.append("Saldo inicial: R$ 0,00")
    return "Confirme o cadastro da conta:\n" + "\n".join(lines)


LIST_REQUEST_HINTS = (
    "liste",
    "listar",
    "listem",
    "quais",
    "mostre",
    "mostrar",
    "ver minhas",
    "minhas contas",
)


def is_slot_answer(message: str, field: str) -> bool:
    if is_complex_message(message):
        return False

    if field == "name":
        value = message.strip()
        lower = value.lower()
        if any(hint in lower for hint in LIST_REQUEST_HINTS):
            return False
        if "conta" in lower and any(
            hint in lower for hint in ("liste", "listar", "quais", "minhas", "cadastrad")
        ):
            return False
        return (
            len(value) >= 2
            and not looks_like_amount(value)
            and is_short_slot_message(value, max_words=6)
        )
    if field == "account_type":
        return parse_account_type(message) is not None
    if field == "institution":
        return is_skip(message) or is_short_slot_message(message, max_words=6)
    if field == "opening_balance":
        return is_skip(message) or looks_like_amount(message)
    if field == "opening_balance_date":
        return parse_opening_balance_date(message) is not None
    return False


def get_wizard_context(session: dict) -> str | None:
    wizard = get_wizard(session)
    if not wizard:
        return None
    field = _next_field(wizard)
    if not field:
        return "Wizard de conta aguardando confirmacao"
    labels = {
        "name": "apelido da conta",
        "account_type": "tipo da conta (corrente, poupança, carteira ou cartão)",
        "institution": "instituição financeira",
        "opening_balance": "saldo inicial",
        "opening_balance_date": "data do saldo inicial",
    }
    return f"Wizard de conta aguardando: {labels.get(field, field)}"



def wizard_to_tool_call(wizard: dict) -> ToolCall:
    args = {
        "name": wizard["name"],
        "account_type": wizard["account_type"],
        "institution": wizard.get("institution"),
        "opening_balance": wizard.get("opening_balance"),
    }
    if wizard.get("opening_balance_date"):
        args["opening_balance_date"] = wizard["opening_balance_date"]
    return ToolCall(tool="create_account", arguments=args)


def _ask_field(field: str, message: str | None = None) -> AgentResponse:
    return AgentResponse(
        message=message or QUESTIONS[field],
        suggestions=for_account_wizard_field(field),
        source="wizard",
    )


def try_process_account_wizard(session: dict, message: str) -> AgentResponse | None:
    if not get_wizard(session):
        return None
    if wants_account_creation(message) and not is_cancel(message):
        clear_wizard(session)
        return begin_account_wizard(session, message)
    return process_wizard_message(session, message)


def process_wizard_message(session: dict, message: str) -> AgentResponse | None:
    wizard = get_wizard(session)
    if not wizard:
        return None

    if is_cancel(message):
        clear_wizard(session)
        return AgentResponse(message="Cadastro de conta cancelado.", clear_wizard=True, source="wizard")

    next_field = _next_field(wizard)
    if next_field is None:
        _sanitize_wizard_name(wizard)
        if not wizard.get("name"):
            return _ask_field("name")
        lower = message.strip().lower()
        if lower in {"sim", "s", "ok", "confirmo", "isso", "essa", "esse"}:
            return AgentResponse(
                message=_wizard_summary(wizard),
                needs_confirmation=True,
                pending_action=wizard_to_tool_call(wizard).model_dump(),
                tool_used="create_account",
                source="wizard",
            )
        clear_wizard(session)
        return None

    if not is_slot_answer(message, next_field):
        clear_wizard(session)
        return None

    error = _fill_field(wizard, next_field, message)
    if error:
        session[WIZARD_KEY] = wizard
        return AgentResponse(
            message=error,
            suggestions=for_account_wizard_field(next_field),
            source="wizard",
        )

    session[WIZARD_KEY] = wizard
    remaining = _next_field(wizard)
    if remaining is None:
        _sanitize_wizard_name(wizard)
        if not wizard.get("name"):
            return _ask_field("name")
        return AgentResponse(
            message=_wizard_summary(wizard),
            needs_confirmation=True,
            pending_action=wizard_to_tool_call(wizard).model_dump(),
            tool_used="create_account",
            source="wizard",
        )

    return _ask_field(remaining)


def begin_account_wizard(
    session: dict, message: str, initial: dict | None = None
) -> AgentResponse:
    extracted = detect_account_creation(message) or {}
    merged = {**extracted, **(initial or {})}
    start_wizard(session, merged)
    wizard = get_wizard(session)
    assert wizard is not None
    _sanitize_wizard_name(wizard)
    session[WIZARD_KEY] = wizard

    next_field = _next_field(wizard)
    if next_field is None:
        _sanitize_wizard_name(wizard)
        if not wizard.get("name"):
            return _ask_field("name")
        return AgentResponse(
            message=_wizard_summary(wizard),
            needs_confirmation=True,
            pending_action=wizard_to_tool_call(wizard).model_dump(),
            tool_used="create_account",
            source="wizard",
        )
    return _ask_field(next_field)
