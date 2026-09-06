import re

from app.services.text_correction import correct_category_name

ACCOUNT_HINTS = (
    "cadastrar conta",
    "cadastro da conta",
    "cadastro de conta",
    "cadastro conta",
    "nova conta",
    "adicionar conta",
    "criar conta",
    "registrar conta",
    "realize o cadastro",
    "realizar o cadastro",
    "realizar cadastro",
)

ACCOUNT_CREATION_RE = re.compile(
    r"\b(?:cadastrar|cadastre|cadastra|cadastro|criar|crie|cria|adicionar|adicione|adiciona|"
    r"registrar|registre|registra|nova|"
    r"realize|realizar|fa[cç]a)\b"
    r"(?:\s+\w+){0,5}\s+conta\b",
    re.IGNORECASE,
)

CARD_HINTS = (
    "cadastrar cartão",
    "cadastrar cartao",
    "novo cartão",
    "novo cartao",
    "adicionar cartão",
    "adicionar cartao",
    "criar cartão",
    "criar cartao",
    "registrar cartão",
    "registrar cartao",
)

CARD_CREATION_RE = re.compile(
    r"\b(?:cadastrar|cadastre|cadastra|criar|crie|cria|adicionar|adicione|adiciona|"
    r"registrar|registre|registra|novo|nova)\b(?:\s+\w+){0,4}\s+cart[aã]o\b",
    re.IGNORECASE,
)

CLOSING_DAY_RE = re.compile(
    r"(?:fecha(?:mento)?|fechamento)\s*(?:dia\s*)?(\d{1,2})",
    re.IGNORECASE,
)
DUE_DAY_RE = re.compile(
    r"(?:vence(?:mento)?|vencimento)\s*(?:dia\s*)?(\d{1,2})",
    re.IGNORECASE,
)
SETTLEMENT_RE = re.compile(
    r"(?:liquida(?:ção|cao)|liquidação|liquidacao|conta\s+de\s+liquidação|"
    r"conta\s+de\s+liquidacao|pagar\s+(?:com|na|pela))\s+(?:conta\s+)?(.+)$",
    re.IGNORECASE,
)

LIST_ACCOUNT_RE = re.compile(
    r"\b(?:liste|listar|listem|mostre|mostrar|ver|quais)\b.*\bcontas?\b",
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
    "cadastrar categorias",
    "cadastre a categoria",
    "cadastre as categorias",
    "nova categoria",
    "adicionar categoria",
    "criar categoria",
    "criar categorias",
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
    # Criação tem prioridade: "cadastro da conta bancária..." não é listagem
    if wants_account_creation(message):
        return False
    if LIST_ACCOUNT_RE.search(lower):
        return True
    return any(phrase in lower for phrase in LIST_ACCOUNT_PHRASES)


def wants_account_creation(message: str) -> bool:
    if wants_card_creation(message):
        return False
    lower = message.lower().strip()
    if any(hint in lower for hint in ACCOUNT_HINTS):
        return True
    return bool(ACCOUNT_CREATION_RE.search(lower))


def wants_card_creation(message: str) -> bool:
    lower = message.lower().strip()
    if any(hint in lower for hint in CARD_HINTS):
        return True
    return bool(CARD_CREATION_RE.search(lower))


def detect_card_creation(message: str) -> dict | None:
    if not wants_card_creation(message):
        return None
    from app.services.account_wizard import extract_institution
    from app.services.credit_cards import parse_day_of_month
    from app.services.tools import parse_amount

    data: dict = {}
    lower = message.lower().strip()

    institution = extract_institution(message)
    if institution:
        data["institution"] = institution
        data["institution_asked"] = True

    closing_match = CLOSING_DAY_RE.search(lower)
    if closing_match:
        day = int(closing_match.group(1))
        if 1 <= day <= 31:
            data["closing_day"] = day

    due_match = DUE_DAY_RE.search(lower)
    if due_match:
        day = int(due_match.group(1))
        if 1 <= day <= 31:
            data["due_day"] = day

    if "fecha" not in lower and "fechamento" not in lower:
        for token in re.findall(r"\bfech(?:a|amento)?\s*(\d{1,2})\b", lower):
            day = int(token)
            if 1 <= day <= 31 and "closing_day" not in data:
                data["closing_day"] = day

    amount = parse_amount(lower)
    if amount and ("limite" in lower or "limit" in lower):
        data["credit_limit"] = amount
        data["credit_limit_asked"] = True

    settlement_match = SETTLEMENT_RE.search(message)
    if settlement_match:
        name = settlement_match.group(1).strip(" .,-")
        if len(name) >= 2:
            data["settlement_account_name"] = name[:100]

    name = _extract_card_name(message)
    if name:
        data["name"] = name

    return data


def _extract_card_name(message: str) -> str | None:
    match = CARD_CREATION_RE.search(message)
    if not match:
        return None
    remainder = message[match.end() :].strip()
    if not remainder:
        return None
    remainder = re.sub(
        r"\b(?:de|do|da|com|limite|fechamento|vencimento|liquidação|liquidacao|"
        r"conta|cartão|cartao|crédito|credito)\b.*$",
        "",
        remainder,
        flags=re.IGNORECASE,
    ).strip(" -,.")
    remainder = re.sub(r"\s+", " ", remainder).strip()
    if len(remainder) >= 2:
        return remainder[:100]
    from app.services.account_wizard import extract_institution

    institution = extract_institution(message)
    if institution:
        return institution[:100]
    return None


CARD_UPDATE_RE = re.compile(
    r"\b(?:alterar|altere|atualizar|atualize|mudar|mude|corrigir|corrija|editar|edite)\b.*\bcart[aã]o\b",
    re.IGNORECASE,
)
CARD_REFERENCE_RE = re.compile(
    r"(?:do|da|de)\s+cart[aã]o\s+(.+?)(?:\s+(?:para|com|e)\b|\s*$)",
    re.IGNORECASE,
)
CARD_REFERENCE_AFTER_RE = re.compile(
    r"cart[aã]o\s+(?:de\s+)?(.+?)(?:\s+(?:para|com)\b|\s*$)",
    re.IGNORECASE,
)
CARD_UPDATE_HINTS = (
    "fechamento",
    "vencimento",
    "liquidação",
    "liquidacao",
    "limite",
    "instituição",
    "instituicao",
    "apelido",
)


def _extract_card_reference(message: str) -> str | None:
    for pattern in (CARD_REFERENCE_RE, CARD_REFERENCE_AFTER_RE):
        match = pattern.search(message)
        if match:
            name = match.group(1).strip(" .,-")
            name = re.sub(
                r"\b(?:por favor|agora|hoje|por\s+favor)\b.*$",
                "",
                name,
                flags=re.IGNORECASE,
            ).strip(" .,-")
            if len(name) >= 2:
                return name[:100]
    return None


def wants_card_delete(message: str) -> bool:
    lower = message.lower().strip()
    if not any(
        hint in lower
        for hint in ("excluir", "exclua", "deletar", "delete", "apagar", "apague", "remover", "remova")
    ):
        return False
    return "cartão" in lower or "cartao" in lower


def detect_card_delete(message: str) -> dict | None:
    if not wants_card_delete(message):
        return None
    data: dict = {}
    card_name = _extract_card_reference(message)
    if card_name:
        data["card_name"] = card_name
    return data


def wants_card_update(message: str) -> bool:
    if wants_card_creation(message) or wants_card_delete(message):
        return False
    lower = message.lower().strip()
    if "cartão" not in lower and "cartao" not in lower:
        return False
    if CARD_UPDATE_RE.search(lower):
        return True
    return any(hint in lower for hint in CARD_UPDATE_HINTS) and any(
        hint in lower
        for hint in (
            "alterar",
            "altere",
            "atualizar",
            "atualize",
            "mudar",
            "mude",
            "corrigir",
            "corrija",
            "editar",
            "edite",
            "trocar",
            "troque",
        )
    )


def detect_card_update(message: str) -> dict | None:
    if not wants_card_update(message):
        return None
    from app.services.account_wizard import extract_institution
    from app.services.tools import parse_amount

    data: dict = {}
    lower = message.lower().strip()

    card_name = _extract_card_reference(message)
    if card_name:
        data["card_name"] = card_name

    closing_match = CLOSING_DAY_RE.search(lower)
    if closing_match:
        day = int(closing_match.group(1))
        if 1 <= day <= 31:
            data["closing_day"] = day

    due_match = DUE_DAY_RE.search(lower)
    if due_match:
        day = int(due_match.group(1))
        if 1 <= day <= 31:
            data["due_day"] = day
    elif "vencimento" in lower:
        para_match = re.search(r"para\s+dia\s+(\d{1,2})\b", lower)
        if para_match:
            day = int(para_match.group(1))
            if 1 <= day <= 31:
                data["due_day"] = day

    if "closing_day" not in data and "fechamento" in lower:
        para_match = re.search(r"para\s+dia\s+(\d{1,2})\b", lower)
        if para_match:
            day = int(para_match.group(1))
            if 1 <= day <= 31:
                data["closing_day"] = day

    settlement_match = SETTLEMENT_RE.search(message)
    if settlement_match:
        name = settlement_match.group(1).strip(" .,-")
        if len(name) >= 2:
            data["settlement_account_name"] = name[:100]

    amount = parse_amount(lower)
    if amount and ("limite" in lower or "limit" in lower):
        data["credit_limit"] = amount

    if any(kw in lower for kw in ("instituição", "instituicao", "banco")):
        institution = extract_institution(message)
        if institution:
            data["institution"] = institution

    return data


def wants_list_categories(message: str) -> bool:
    lower = message.lower().strip()
    if CATEGORY_CREATION_RE.search(lower):
        return False
    if any(hint in lower for hint in CATEGORY_HINTS):
        return False
    if LIST_CATEGORY_RE.search(lower):
        return True
    return any(phrase in lower for phrase in LIST_CATEGORY_PHRASES)


def detect_list_categories(message: str) -> dict:
    data: dict = {}
    category_type = _parse_category_type(message)
    if category_type:
        data["type"] = category_type
    return data


def wants_category_update(message: str) -> bool:
    if not CORRECTION_VERB_RE.search(message):
        return False
    lower = message.lower()
    return bool(re.search(r"\bcategor(?:ia|ias)\b", lower))


def detect_category_update(message: str) -> dict | None:
    if not wants_category_update(message):
        return None
    data: dict = {}
    # "atualiza a categoria X para o tipo Receita"
    named = re.search(
        r"\bcategor(?:ia|ias)\s+([A-Za-zÀ-ÿ0-9][\wÀ-ÿ0-9 &/\-]{1,80}?)"
        r"(?:\s+(?:para|pra|pro|como|com|de|do|da)\b|\s*$)",
        message,
        re.IGNORECASE,
    )
    if named:
        raw_name = named.group(1).strip(" -,.")
        raw_name = re.sub(
            r"\b(?:para|pra|pro|como|tipo|despesa|receita)\b.*$",
            "",
            raw_name,
            flags=re.IGNORECASE,
        ).strip(" -,.")
        if len(raw_name) >= 2:
            data["category_name"] = correct_category_name(raw_name)[:100]

    category_type = _parse_category_type(message)
    if category_type:
        data["type"] = category_type

    rename = re.search(
        r"\b(?:para|pra|como)\s+(?:o\s+nome\s+)?([A-Za-zÀ-ÿ][\wÀ-ÿ &\-]{1,60})",
        message,
        re.IGNORECASE,
    )
    if rename and "tipo" not in message.lower():
        candidate = rename.group(1).strip(" -,.")
        if candidate.lower() not in {
            "despesa",
            "despesas",
            "receita",
            "receitas",
            "tipo",
        }:
            data["name"] = correct_category_name(candidate)[:100]

    keywords_match = re.search(
        r"\b(?:palavras?-chave|keywords?)\s*:?\s*(.+)$",
        message,
        re.IGNORECASE,
    )
    if keywords_match:
        data["keywords"] = keywords_match.group(1).strip()[:500]

    return data or None


def wants_category_delete(message: str) -> bool:
    lower = message.lower()
    if not any(
        w in lower
        for w in ("exclu", "apag", "delet", "remover", "remova", "remove")
    ):
        return False
    return bool(re.search(r"\bcategor(?:ia|ias)\b", lower))


def detect_category_delete(message: str) -> dict | None:
    if not wants_category_delete(message):
        return None
    data: dict = {}
    named = re.search(
        r"\bcategor(?:ia|ias)\s+([A-Za-zÀ-ÿ0-9][\wÀ-ÿ0-9 &/\-]{1,80})",
        message,
        re.IGNORECASE,
    )
    if named:
        raw_name = named.group(1).strip(" -,.")
        if len(raw_name) >= 2:
            data["category_name"] = correct_category_name(raw_name)[:100]
    return data or {}


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


def parse_category_names(raw: str, *, allow_e_split: bool = False) -> list[str]:
    """Divide lista de categorias.

    Com vírgulas: 'Presente, Restaurante e Lazer' → 3 nomes.
    Sem vírgula: 'Vale e Auxílio' permanece um nome, salvo allow_e_split
    (comando no plural: 'cadastre as categorias Presente e Lazer').
    """
    cleaned = (raw or "").strip().lstrip(":").strip()
    if not cleaned:
        return []
    cleaned = CATEGORY_NAME_NOISE_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -,.")
    if not cleaned:
        return []
    if "," in cleaned:
        parts = re.split(r"\s*,\s*|\s+e\s+", cleaned, flags=re.IGNORECASE)
    elif allow_e_split:
        parts = re.split(r"\s+e\s+", cleaned, flags=re.IGNORECASE)
    else:
        parts = [cleaned]
    names: list[str] = []
    seen: set[str] = set()
    for part in parts:
        part = part.strip(" -,.")
        if len(part) < 2:
            continue
        name = correct_category_name(part)[:100]
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def _extract_category_name(text: str) -> str | None:
    names = _extract_category_names(text)
    return names[0] if names else None


def _extract_category_names(text: str) -> list[str]:
    match = CATEGORY_CREATION_RE.search(text)
    if not match:
        return []
    plural = bool(re.search(r"categorias\b", match.group(0), re.IGNORECASE))
    return parse_category_names(text[match.end() :], allow_e_split=plural)


def detect_category_creation(message: str) -> dict | None:
    if not CATEGORY_CREATION_RE.search(message):
        return None
    data: dict = {}
    names = _extract_category_names(message)
    if len(names) > 1:
        data["names"] = names
    elif len(names) == 1:
        data["name"] = names[0]
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

CORRECT_TRANSFER_RE = re.compile(
    r"\b(?:correto|certo)\s+[eé]\s+(?:de|da|do)\s+(.+?)\s+(?:para|pra|pro)\s+(.+?)(?:\.|$)",
    re.IGNORECASE,
)


def _strip_account_hint(raw: str) -> str:
    cleaned = raw.strip(" -,.")
    cleaned = re.sub(r"^(?:o|a|os|as)\s+", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned[:100]


def wants_transfer(message: str) -> bool:
    return bool(TRANSFER_RE.search(message))


TRANSFER_CORRECTION_RE = re.compile(
    r"\b(?:transfer[eê]ncia|transferencia)\b",
    re.IGNORECASE,
)

CORRECTION_VERB_RE = re.compile(
    r"\b(?:corrija|corrigir|correção|correcao|editar|edite|alterar|altere|mudar|mude|trocar|troque|atualizar|atualize)\b",
    re.IGNORECASE,
)


def wants_transfer_correction(message: str) -> bool:
    if not CORRECTION_VERB_RE.search(message):
        return False
    return wants_transfer(message) or bool(TRANSFER_CORRECTION_RE.search(message))


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


def _has_income_amount_signal(lower: str) -> bool:
    """Valor + sinal claro de receita (recebi, entrada, salário…)."""
    from app.services.tools import parse_amount

    if not parse_amount(lower):
        return False
    if CORRECTION_VERB_RE.search(lower):
        return False
    if wants_category_creation(lower) or wants_account_creation(lower):
        return False
    if wants_card_update(lower) or wants_card_delete(lower) or wants_card_creation(lower):
        return False

    income_markers = (
        "recebi",
        "ganhei",
        "receita",
        "receitas",
        "salario",
        "salário",
        "rendimento",
        "freelance",
    )
    if any(h in lower for h in income_markers):
        # "despesa de receita" / ambíguo raro: se há gasto explícito, não é receita
        if any(
            h in lower
            for h in ("gastei", "paguei", "comprei", "despesa", "gasto")
        ) and not re.search(r"\bentradas?\b", lower):
            return False
        return True
    # "tive uma entrada", "entrada de 550", "uma entrada referente"
    if re.search(r"\bentradas?\b", lower):
        return True
    if re.search(r"\b(?:tive|tenho|houve)\s+(?:uma?\s+)?(?:entrada|receita)\b", lower):
        return True
    return False


def _has_expense_amount_signal(lower: str) -> bool:
    """Valor + sinal claro de despesa (verbo, referente, valor no início + cartão/conta)."""
    from app.services.tools import parse_amount

    if not parse_amount(lower):
        return False
    # CRUD / correção de conta-cartão-lançamento não é novo gasto
    if CORRECTION_VERB_RE.search(lower):
        return False
    if wants_card_update(lower) or wants_card_delete(lower) or wants_card_creation(lower):
        return False
    if wants_account_creation(lower):
        return False
    if _has_income_amount_signal(lower):
        return False
    if any(
        w in lower
        for w in (
            "excluir",
            "exclua",
            "deletar",
            "apagar",
            "remover",
            "atualizar",
            "atualize",
            "limite",
        )
    ):
        # "limite 27800" no cadastro/edição de cartão
        if "cartão" in lower or "cartao" in lower:
            return False

    expense_verbs = (
        "gastei",
        "paguei",
        "comprei",
        "gasto",
        "despesa",
        "debito",
        "débito",
        "lance",
        "lançar",
        "lancar",
        "custo",
        "custei",
        "curso de",
    )
    if any(h in lower for h in expense_verbs):
        return True
    # "tive" sozinho é ambíguo ("tive uma entrada" vs "tive o custo");
    # só conta como despesa se houver contexto de gasto.
    if re.search(r"\btive\b", lower) and any(
        h in lower
        for h in (
            "despesa",
            "gasto",
            "custo",
            "compra",
            "paguei",
            "gastei",
            "cartão",
            "cartao",
        )
    ):
        return True
    if "referente" in lower and not re.search(r"\bentradas?\b", lower):
        return True
    # Valor no início + cartão/conta (ex.: "17,54 do presente no cartão")
    if re.match(r"^\s*(?:r\$\s*)?\d", lower) and (
        "cartão" in lower
        or "cartao" in lower
        or re.search(r"\b(?:na conta|da conta|conta da|conta do)\b", lower)
    ):
        return True
    return False


def wants_register_expense(message: str) -> bool:
    lower = message.lower().strip()
    if wants_pay_invoice(message):
        return False
    if wants_planned_movement(message):
        return False
    if _is_list_or_summary_context(lower):
        return False
    if wants_list_categories(message) or wants_list_accounts(message):
        return False
    if wants_transfer(message) or wants_category_creation(message):
        return False
    if wants_account_creation(message) or wants_card_creation(message):
        return False
    if wants_card_update(message) or wants_card_delete(message):
        return False
    if CORRECTION_VERB_RE.search(lower):
        return False
    # Receita tem prioridade quando o sinal é inequívoco
    if _has_income_amount_signal(lower):
        return False
    if lower in INCOME_ONLY_WORDS:
        return False
    if re.search(r"\b(?:isso\s+)?(?:é|e)\s+(?:uma?\s+)?receita\b", lower):
        return False
    if lower in EXPENSE_ONLY_WORDS:
        return True
    if REGISTER_EXPENSE_RE.search(lower):
        return True
    if len(lower.split()) <= 6 and "despesa" in lower and "receita" not in lower:
        if re.search(r"\b(?:quero|lancar|lançar|lance|registrar|registre)\b", lower):
            return True
    if _has_expense_amount_signal(lower):
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
    if wants_account_creation(message) or wants_card_creation(message):
        return False
    if CORRECTION_VERB_RE.search(lower):
        return False
    if lower in INCOME_ONLY_WORDS:
        return True
    if REGISTER_INCOME_RE.search(lower):
        return True
    if len(lower.split()) <= 6 and "receita" in lower and "despesa" not in lower:
        if re.search(
            r"\b(?:quero|lancar|lançar|lance|registrar|registre|isso|é|e)\b",
            lower,
        ):
            return True
    if re.search(r"\b(?:isso\s+)?(?:é|e)\s+(?:uma?\s+)?receita\b", lower):
        return True
    if _has_income_amount_signal(lower):
        return True
    return False


def detect_transfer(message: str) -> dict | None:
    if not wants_transfer(message) and not TRANSFER_FROM_TO_RE.search(message):
        return None
    data: dict = {}
    match = CORRECT_TRANSFER_RE.search(message)
    if not match:
        matches = list(TRANSFER_FROM_TO_RE.finditer(message))
        match = matches[-1] if matches else None
    if match:
        from_raw = _strip_account_hint(match.group(1))
        to_raw = _strip_account_hint(match.group(2))
        if len(from_raw) >= 2:
            data["from_account_name"] = from_raw
        if len(to_raw) >= 2:
            data["to_account_name"] = to_raw
    return data


LIST_INVOICE_RE = re.compile(
    r"\b(?:fatura|faturas)\b",
    re.IGNORECASE,
)

PAY_INVOICE_RE = re.compile(
    r"\b(?:paguei|pagar|pagamento|baix(?:ar|ei|a)|liquid(?:ar|ei|a)|quit(?:ar|ei))\b.*\bfatura\b"
    r"|\bfatura\b.*\b(?:paguei|pagar|pagamento|baix(?:ar|ei|a)|liquid(?:ar|ei|a)|quit(?:ar|ei))\b",
    re.IGNORECASE,
)

PAY_INVOICE_CARD_RE = re.compile(
    r"(?:\bcart[aã]o\b.*?\b(?:do|da|de)\s+|fatura\b.*?\bcart[aã]o\b\s+)([^,.]+)",
    re.IGNORECASE,
)

PAY_INVOICE_FROM_ACCOUNT_RE = re.compile(
    r"\b(?:com|da|de|pela|pelo)\s+(?:a\s+)?conta\s+([^,.]+)",
    re.IGNORECASE,
)


def wants_list_invoices(message: str) -> bool:
    lower = message.lower().strip()
    if wants_pay_invoice(message):
        return False
    if not LIST_INVOICE_RE.search(lower):
        return False
    return any(
        w in lower
        for w in (
            "qual",
            "quanto",
            "ver",
            "listar",
            "mostrar",
            "quando",
            "vence",
            "fechamento",
            "limite",
            "disponível",
            "disponivel",
        )
    ) or bool(re.search(r"\bfatura\b.*\b(?:cart[aã]o|nubank|itau|itaú)", lower))


def wants_pay_invoice(message: str) -> bool:
    return bool(PAY_INVOICE_RE.search(message.lower().strip()))


def detect_invoice_query(message: str) -> dict:
    data: dict = {}
    lower = message.lower()
    for hint in ("nubank", "itau", "itaú", "bradesco", "santander", "inter", "c6"):
        if hint in lower:
            data["account_name"] = hint.title() if hint != "itau" else "Itaú"
            break
    return data


def detect_pay_invoice(message: str) -> dict:
    from app.services.credit_cards import parse_invoice_period_hint

    data: dict = {}
    lower = message.lower()
    card_match = PAY_INVOICE_CARD_RE.search(message)
    if card_match:
        data["account_name"] = card_match.group(1).strip()[:100]
    from_match = PAY_INVOICE_FROM_ACCOUNT_RE.search(message)
    if from_match:
        data["from_account_name"] = from_match.group(1).strip()[:100]
    period = parse_invoice_period_hint(message)
    if period:
        data["due_month"], data["due_year"] = period
    for hint, label in (
        ("nubank", "Nubank"),
        ("itau", "Itaú"),
        ("itaú", "Itaú"),
        ("corrente", "Corrente"),
        ("carteira", "Carteira"),
    ):
        if hint in lower and "from_account_name" not in data:
            if f"com conta {hint}" in lower or f"da conta {hint}" in lower:
                data["from_account_name"] = label
    return data
