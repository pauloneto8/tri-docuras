"""Toolkit tipado do agente v2.

Registry único: cada ferramenta tem nome, descrição em pt-BR, JSON Schema dos
parâmetros, tipo (`read`/`write`) e handler. Ferramentas de escrita NÃO são
executadas aqui — o brain acumula num plano pendente e `confirm.py` executa.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from app.schemas import (
    BudgetStatusInput,
    CreateAccountInput,
    CreateCardInput,
    CreateCategoryInput,
    DeleteCardInput,
    DeleteCategoryInput,
    DeleteTransactionInput,
    ListCategoriesInput,
    ListTransactionsInput,
    PayInvoiceInput,
    RealizePlannedInput,
    RegisterExpenseInput,
    RegisterIncomeInput,
    RegisterTransferInput,
    SummaryInput,
    ToolCall,
    UpdateAccountInput,
    UpdateCardInput,
    UpdateCategoryInput,
    UpdateTransactionInput,
    UpdateTransferInput,
)

ToolKind = Literal["read", "write"]


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    kind: ToolKind
    schema_model: Optional[type] = None
    handler: Optional[Callable[..., Any]] = None

    model_config = {"arbitrary_types_allowed": True}

    def to_openai_tool(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": compact_schema(self.parameters),
            },
        }


def compact_schema(node: Any) -> Any:
    """Tira o ruído que o pydantic injeta no JSON Schema (`title`, `anyOf` com
    `null`, `default: null`).

    O toolkit inteiro é reenviado em **cada** iteração do loop, então esse ruído
    é pago a cada chamada: nos modelos do Groq free ele sozinho estourava o
    limite de 8.000 tokens/min. Tipo, enum, formato e limites continuam intactos;
    campo opcional continua opcional por não estar em `required`.
    """
    if isinstance(node, list):
        return [compact_schema(item) for item in node]
    if not isinstance(node, dict):
        return node

    out: Dict[str, Any] = {}
    for key, value in node.items():
        if key == "title":
            continue
        if key == "default" and value is None:
            continue
        out[key] = compact_schema(value)

    branches = out.get("anyOf")
    if isinstance(branches, list):
        real = [
            branch
            for branch in branches
            if not (isinstance(branch, dict) and branch.get("type") == "null")
        ]
        if len(real) == 1 and len(branches) <= 2:
            collapsed = {key: value for key, value in out.items() if key != "anyOf"}
            for key, value in real[0].items():
                collapsed.setdefault(key, value)
            return collapsed
    return out


def _schema_of(model) -> Dict[str, Any]:
    schema = model.model_json_schema()
    props = schema.get("properties") or {}
    req = [r for r in (schema.get("required") or []) if r in props]
    return {
        "type": "object",
        "properties": props,
        "required": req,
        "additionalProperties": schema.get("additionalProperties", False),
    }


# --- Handlers de leitura -------------------------------------------------

def _h_list_transactions(db, user_id, args):
    from app.services.tools import execute_tool

    clean = {k: v for k, v in args.items() if not str(k).startswith("_")}
    return execute_tool(db, user_id, ToolCall(tool="list_transactions", arguments=clean))


def _h_list_accounts(db, user_id, args):
    from app.services.tools import execute_tool

    return execute_tool(db, user_id, ToolCall(tool="list_accounts", arguments={}))


def _h_list_categories(db, user_id, args):
    from app.services.tools import execute_tool

    return execute_tool(db, user_id, ToolCall(tool="list_categories", arguments=args))


def _h_get_summary(db, user_id, args):
    from app.services.tools import execute_tool

    return execute_tool(db, user_id, ToolCall(tool="get_summary", arguments=args))


def _h_get_budget_status(db, user_id, args):
    from app.services.tools import execute_tool

    return execute_tool(db, user_id, ToolCall(tool="get_budget_status", arguments=args))


def _h_list_invoices(db, user_id, args):
    from app.services.tools import execute_tool

    return execute_tool(db, user_id, ToolCall(tool="list_invoices", arguments=args))


def _h_categorize(db, user_id, args):
    from app.services.tools import execute_tool

    return execute_tool(db, user_id, ToolCall(tool="categorize", arguments=args))


def _h_search_transactions(db, user_id, args):
    from app.services.agent_reads import search_transactions

    return search_transactions(db, user_id, **args)


def _h_get_balances(db, user_id, args):
    from app.services.agent_reads import get_balances

    return get_balances(db, user_id, **args)


def _h_get_cashflow_projection(db, user_id, args):
    from app.services.agent_reads import get_cashflow_projection

    return get_cashflow_projection(db, user_id, **args)


def _h_compare_periods(db, user_id, args):
    from app.services.agent_reads import compare_periods

    return compare_periods(db, user_id, **args)


def _h_spending_breakdown(db, user_id, args):
    from app.services.agent_reads import spending_breakdown

    return spending_breakdown(db, user_id, **args)


def _h_list_upcoming_bills(db, user_id, args):
    from app.services.agent_reads import list_upcoming_bills

    return list_upcoming_bills(db, user_id, **args)


def _h_list_recurring_and_installments(db, user_id, args):
    from app.services.agent_reads import list_recurring_and_installments

    return list_recurring_and_installments(db, user_id)


def _h_get_invoice_detail(db, user_id, args):
    from app.services.agent_reads import get_invoice_detail

    return get_invoice_detail(db, user_id, **args)


# Esquemas das leituras novas (curtos e explícitos) -------------------------
_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "description": "Texto/descrição (tolera erro de digitação)"},
        "amount": {"type": "string", "description": "Valor exato, ex.: '45.90'"},
        "date_from": {"type": "string", "description": "Data inicial YYYY-MM-DD"},
        "date_to": {"type": "string", "description": "Data final YYYY-MM-DD"},
        "account": {"type": "string"},
        "card": {"type": "string"},
        "category": {"type": "string"},
        "status": {"type": "string", "enum": ["planned", "actual"]},
        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
    },
    "required": [],
    "additionalProperties": False,
}
_BALANCES_SCHEMA = {
    "type": "object",
    "properties": {"as_of": {"type": "string", "description": "YYYY-MM-DD"}},
    "required": [],
    "additionalProperties": False,
}
_CASHFLOW_SCHEMA = {
    "type": "object",
    "properties": {"days": {"type": "integer", "minimum": 1, "maximum": 180}},
    "required": [],
    "additionalProperties": False,
}
_COMPARE_SCHEMA = {
    "type": "object",
    "properties": {
        "year_a": {"type": "integer"},
        "month_a": {"type": "integer"},
        "year_b": {"type": "integer"},
        "month_b": {"type": "integer"},
    },
    "required": ["year_a", "month_a", "year_b", "month_b"],
    "additionalProperties": False,
}
_BREAKDOWN_SCHEMA = {
    "type": "object",
    "properties": {
        "year": {"type": "integer"},
        "month": {"type": "integer"},
        "group_by": {"type": "string", "enum": ["category", "account", "card", "description"]},
        "kind": {"type": "string", "enum": ["expense", "income"]},
    },
    "required": [],
    "additionalProperties": False,
}
_UPCOMING_SCHEMA = {
    "type": "object",
    "properties": {"days": {"type": "integer", "minimum": 1, "maximum": 90}},
    "required": [],
    "additionalProperties": False,
}
_RECURRING_SCHEMA = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
_INVOICE_DETAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "card": {"type": "string"},
        "month": {"type": "integer"},
        "year": {"type": "integer"},
    },
    "required": [],
    "additionalProperties": False,
}


def build_toolkit() -> Dict[str, ToolSpec]:
    tools: Dict[str, ToolSpec] = {}

    def add_read(name, description, schema, handler):
        tools[name] = ToolSpec(
            name=name, description=description, parameters=schema, kind="read", handler=handler
        )

    def add_write(name, description, model):
        tools[name] = ToolSpec(
            name=name,
            description=description,
            parameters=_schema_of(model),
            kind="write",
            schema_model=model,
        )

    # Leituras
    add_read("list_transactions", "Lista os lançamentos mais recentes.", _schema_of(ListTransactionsInput), _h_list_transactions)
    add_read("list_accounts", "Lista contas bancárias e cartões do usuário.", {"type": "object", "properties": {}, "required": [], "additionalProperties": False}, _h_list_accounts)
    add_read("list_categories", "Lista categorias cadastradas.", _schema_of(ListCategoriesInput), _h_list_categories)
    add_read("get_summary", "Resumo financeiro do mês/dia/semana (receitas, despesas, saldo, por categoria).", _schema_of(SummaryInput), _h_get_summary)
    add_read("get_budget_status", "Status dos orçamentos por categoria.", _schema_of(BudgetStatusInput), _h_get_budget_status)
    add_read("list_invoices", "Lista faturas de cartão de crédito.", {"type": "object", "properties": {"account_name": {"type": "string"}, "limit": {"type": "integer"}}, "required": [], "additionalProperties": False}, _h_list_invoices)
    add_read("categorize", "Sugere categoria para uma descrição.", {"type": "object", "properties": {"description": {"type": "string"}, "type": {"type": "string", "enum": ["expense", "income"]}}, "required": ["description"], "additionalProperties": False}, _h_categorize)
    add_read("search_transactions", "Busca lançamentos por texto/valor/data/conta/cartão/categoria/status e devolve ids. OBRIGATÓRIA antes de editar ou excluir.", _SEARCH_SCHEMA, _h_search_transactions)
    add_read("get_balances", "Saldos atuais das contas e resumo dos cartões (cálculo em Python).", _BALANCES_SCHEMA, _h_get_balances)
    add_read("get_cashflow_projection", "Projeção de caixa: previstos pendentes + faturas a vencer no período.", _CASHFLOW_SCHEMA, _h_get_cashflow_projection)
    add_read("compare_periods", "Compara dois meses (receitas, despesas, resultado e diferenças).", _COMPARE_SCHEMA, _h_compare_periods)
    add_read("spending_breakdown", "Despesas/receitas do mês agrupadas por categoria, conta, cartão ou descrição.", _BREAKDOWN_SCHEMA, _h_spending_breakdown)
    add_read("list_upcoming_bills", "Contas a vencer e faturas nos próximos N dias.", _UPCOMING_SCHEMA, _h_list_upcoming_bills)
    add_read("list_recurring_and_installments", "Lançamentos fixos ativos e planos parcelados.", _RECURRING_SCHEMA, _h_list_recurring_and_installments)
    add_read("get_invoice_detail", "Detalha uma fatura de cartão e seus movimentos.", _INVOICE_DETAIL_SCHEMA, _h_get_invoice_detail)

    # Escritas (executadas só após confirmação)
    add_write("register_expense", "Novo lançamento de despesa (conta ou cartão; à vista, fixo ou parcelado; previsto ou realizado).", RegisterExpenseInput)
    add_write(
        "register_income",
        "Novo lançamento de receita. Use quando o usuário disser que recebeu, "
        "entrou, ganhou ou foi creditado dinheiro (salário, freela, vale "
        "refeição, reembolso, entrada, pix recebido) — não quando é despesa.",
        RegisterIncomeInput,
    )
    add_write("register_transfer", "Transferência entre contas (não é receita nem despesa).", RegisterTransferInput)
    add_write("realize_planned", "Converte um previsto em realizado.", RealizePlannedInput)
    add_write("update_transfer", "Corrige uma transferência existente (origem/destino/valor/data).", UpdateTransferInput)
    add_write("update_transaction", "Edita lançamento existente (conta/categoria/valor/descrição/tipo/fatura/escopo de parcelas).", UpdateTransactionInput)
    add_write("update_account", "Edita conta bancária.", UpdateAccountInput)
    add_write("update_card", "Edita cartão de crédito.", UpdateCardInput)
    add_write("delete_card", "Exclui cartão de crédito.", DeleteCardInput)
    add_write("delete_transaction", "Exclui lançamento existente.", DeleteTransactionInput)
    add_write("create_account", "Cadastra conta bancária.", CreateAccountInput)
    add_write("create_card", "Cadastra cartão de crédito.", CreateCardInput)
    add_write("create_category", "Cadastra categoria.", CreateCategoryInput)
    add_write("update_category", "Atualiza categoria.", UpdateCategoryInput)
    add_write("delete_category", "Exclui categoria sem lançamentos.", DeleteCategoryInput)
    add_write("pay_invoice", "Paga fatura de cartão.", PayInvoiceInput)

    return tools


def openai_tools(toolkit: Dict[str, ToolSpec]) -> List[dict]:
    return [spec.to_openai_tool() for spec in toolkit.values()]


def validate_write(spec: ToolSpec, args: Dict[str, Any]) -> Dict[str, Any]:
    """Valida argumentos de uma escrita. Lança ValidationError se inválido."""
    if spec.schema_model is None:
        return args
    clean = {k: v for k, v in args.items() if not str(k).startswith("_")}
    model = spec.schema_model(**clean)
    return model.model_dump(exclude_unset=True, exclude_none=True)


def run_read(spec: ToolSpec, db, user_id: int, args: Dict[str, Any]) -> Any:
    if spec.handler is None:
        return {"error": "ferramenta de leitura sem handler"}
    clean = {k: v for k, v in args.items() if not str(k).startswith("_")}
    return spec.handler(db, user_id, clean)
