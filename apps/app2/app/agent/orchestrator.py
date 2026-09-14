"""Orquestrador multi-etapas (Fase 5 do plano `.cursor/plans/agente-inteligencia-proativa.md`).

Diferente das Fases 1-3 (`app/agent/claude.py`), aqui usamos o SDK oficial da
Anthropic (`anthropic`, novo em `requirements.txt`) porque só o SDK oferece o
Tool Runner (`client.beta.messages.tool_runner`) — o loop agentico que decide
quais ferramentas chamar e quantas vezes. Continua sendo Claude usado só para
raciocinar sobre dados já calculados: as únicas ferramentas expostas ao
orquestrador são de LEITURA (as mesmas já usadas em `execute_tool`); ele nunca
recebe `register_*`/`update_*`/`delete_*`. Qualquer ação que o orquestrador
queira sugerir fica só no texto da resposta — se o usuário topar, a mensagem
seguinte dele volta ao fluxo normal de `process_message` (Groq/regra), que já
enxerga o histórico recente da conversa (`build_intent_context`) e passa pela
confirmação de escrita de sempre. O orquestrador nunca escreve direto.

Desligado por padrão via `ENABLE_AI_ORCHESTRATOR`/`ANTHROPIC_API_KEY` vazios.
"""

import json
import logging
import re

from anthropic import AsyncAnthropic
from anthropic.lib.tools import beta_async_tool

from app.config import settings
from app.schemas import ToolCall
from app.services.tools import execute_tool, parse_amount

logger = logging.getLogger(__name__)

# Mesmo padrão de validação anti-alucinação da Fase 2 (`app/services/insights.py`):
# todo valor "R$ x,xx" citado na resposta final precisa ser um dos valores que
# alguma ferramenta de leitura realmente devolveu nesta execução.
_MONEY_RE = re.compile(r"R\$\s?-?\d{1,3}(?:\.\d{3})*,\d{2}")

_BROAD_VERB_RE = re.compile(
    r"\b("
    r"revis\w*|organiz\w*|analis\w*|avali\w*|planej\w*|otimiz\w*"
    r"|onde\s+(eu\s+)?(posso|estou|consigo)\s+\w*(cort|gast|econom)\w*"
    r"|sugest(ão|oes|ões)\s+de\s+corte"
    r"|me\s+(ajuda|ajude)\s+a\s+(organizar|planejar|entender)"
    r")\b",
    re.IGNORECASE,
)
_MIN_BROAD_LENGTH = 40

ORCHESTRATOR_SYSTEM_PROMPT = """Voce e o assistente financeiro do AssistFin, respondendo em
portugues do Brasil a um pedido amplo do usuario (ex.: "revise meus gastos do
mes e sugira cortes").

Use as ferramentas de leitura disponiveis (list_transactions, get_summary,
get_budget_status, list_categories, list_invoices) para reunir os dados antes
de responder — nao adivinhe numeros. Chame quantas ferramentas forem
necessarias (limite de turnos existe, entao va direto ao ponto).

Regras obrigatorias:
- Copie valores monetarios EXATAMENTE como as ferramentas devolveram (ex.:
  "R$ 1.234,56"); nunca some, arredonde ou invente um valor que nao veio de
  uma ferramenta.
- Voce so LE dados — nao tem nenhuma ferramenta de escrita. Se fizer sentido
  sugerir uma acao (categorizar transacoes, ajustar orcamento, etc.), proponha
  em texto, como uma pergunta clara que o usuario possa responder diretamente
  (ex.: "Quer que eu categorize os R$ 320,00 de mercado como Alimentacao?").
  Nunca diga que ja fez a acao.
- Resposta curta e direta: um resumo com os numeros relevantes seguido de, no
  maximo, 2-3 sugestoes concretas. Sem markdown, sem tabelas.
"""


def looks_like_broad_request(message: str) -> bool:
    """Heuristica do plano (Fase 5): mensagem longa, com verbo de analise/
    revisao ampla, sem um valor monetario explicito — presenca de valor
    sugere uma acao unica (registrar/editar), que o caminho normal (Groq/
    regra) ja resolve melhor e mais barato.
    """
    text = message.strip()
    if len(text) < _MIN_BROAD_LENGTH:
        return False
    if not _BROAD_VERB_RE.search(text):
        return False
    if parse_amount(text.lower()):
        return False
    return True


async def orchestrator_configured() -> bool:
    return bool(settings.enable_ai_orchestrator and settings.anthropic_api_key.strip())


def _json_default(obj):
    return str(obj)


def _build_read_tools(db, user_id: int, known_values: set[str]) -> list:
    """Ferramentas de LEITURA expostas ao orquestrador, presas a `db`/`user_id`
    via closure. Cada uma delega a `execute_tool` — mesmo caminho usado pelo
    resto do agente — e nunca inclui uma ferramenta de escrita na lista.
    """

    def _run(tool_name: str, args: dict) -> str:
        try:
            outcome = execute_tool(db, user_id, ToolCall(tool=tool_name, arguments=args))
            text = json.dumps(outcome["result"], ensure_ascii=False, default=_json_default)
        except Exception as exc:  # noqa: BLE001 — erro vira resultado da tool, nao derruba o loop
            return f"Erro ao consultar: {exc}"
        known_values.update(_MONEY_RE.findall(text))
        return text

    @beta_async_tool
    async def list_transactions(
        limit: int = 10,
        type: str = "all",
        status: str = "all",
        start_date: str | None = None,
        end_date: str | None = None,
        category_id: int | None = None,
    ) -> str:
        """Lista lancamentos do usuario (leitura). Use para ver transacoes especificas,
        nao so totais.

        Args:
            limit: Maximo de lancamentos a retornar (1-100).
            type: "expense", "income", "transfer" ou "all".
            status: "actual" (realizado), "planned" (previsto) ou "all".
            start_date: Data inicial no formato AAAA-MM-DD, opcional.
            end_date: Data final no formato AAAA-MM-DD, opcional.
            category_id: Filtrar por id de categoria, opcional.
        """
        args: dict = {"limit": limit, "type": type, "status": status}
        if start_date:
            args["start_date"] = start_date
        if end_date:
            args["end_date"] = end_date
        if category_id is not None:
            args["category_id"] = category_id
        return _run("list_transactions", args)

    @beta_async_tool
    async def get_summary(year: int | None = None, month: int | None = None) -> str:
        """Resumo financeiro do mes (receita, despesa, saldo). Use para numeros
        agregados do periodo antes de detalhar transacao por transacao.

        Args:
            year: Ano, ex. 2026. Padrao: ano atual.
            month: Mes (1-12). Padrao: mes atual.
        """
        args: dict = {}
        if year is not None:
            args["year"] = year
        if month is not None:
            args["month"] = month
        return _run("get_summary", args)

    @beta_async_tool
    async def get_budget_status(year: int | None = None, month: int | None = None) -> str:
        """Status de orcamento por categoria (gasto vs limite) do mes.

        Args:
            year: Ano, ex. 2026. Padrao: ano atual.
            month: Mes (1-12). Padrao: mes atual.
        """
        args: dict = {}
        if year is not None:
            args["year"] = year
        if month is not None:
            args["month"] = month
        return _run("get_budget_status", args)

    @beta_async_tool
    async def list_categories(type: str | None = None) -> str:
        """Lista as categorias do usuario, opcionalmente filtradas por tipo.

        Args:
            type: "expense" ou "income", opcional (lista as duas se omitido).
        """
        args: dict = {}
        if type in {"expense", "income"}:
            args["type"] = type
        return _run("list_categories", args)

    @beta_async_tool
    async def list_invoices(account_name: str | None = None, limit: int = 12) -> str:
        """Lista faturas de cartao de credito do usuario.

        Args:
            account_name: Nome do cartao, opcional (lista de todos os cartoes se omitido).
            limit: Maximo de faturas a retornar.
        """
        args: dict = {"limit": limit}
        if account_name:
            args["account_name"] = account_name
        return _run("list_invoices", args)

    return [list_transactions, get_summary, get_budget_status, list_categories, list_invoices]


async def run_orchestrator(db, user_id: int, message: str) -> str | None:
    """Roda o Tool Runner do Claude (Sonnet) sobre as ferramentas de leitura.

    Retorna None (o runner cai no fluxo normal de sempre) se a funcionalidade
    estiver desligada, sem chave configurada, se a chamada falhar, ou se a
    resposta final nao tiver texto. Se a resposta citar um valor monetario que
    nenhuma ferramenta devolveu, descarta e devolve uma mensagem generica em
    vez de arriscar mostrar numero inventado — mesma politica da Fase 2.
    """
    if not await orchestrator_configured():
        return None

    known_values: set[str] = set()
    tools = _build_read_tools(db, user_id, known_values)

    try:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        runner = client.beta.messages.tool_runner(
            model=settings.anthropic_model_reasoning,
            max_tokens=1500,
            system=ORCHESTRATOR_SYSTEM_PROMPT,
            tools=tools,
            max_iterations=5,
            output_config={"effort": "medium"},
            messages=[{"role": "user", "content": message}],
        )
        final_message = await runner.until_done()
    except Exception:  # noqa: BLE001 — erro de rede/API cai no fluxo normal, nao derruba o chat
        logger.exception("Falha ao rodar orquestrador Claude (user_id=%s)", user_id)
        return None

    text = "".join(
        block.text for block in final_message.content if getattr(block, "type", None) == "text"
    ).strip()
    if not text:
        return None

    mentions = _MONEY_RE.findall(text)
    if not all(mention in known_values for mention in mentions):
        logger.warning(
            "Resposta do orquestrador descartada por citar valor fora do esperado "
            "(user_id=%s): %r",
            user_id,
            text,
        )
        return (
            "Consegui olhar seus dados, mas prefiro nao arriscar mostrar um numero "
            "que nao bateu direito. Tenta perguntar de um jeito mais especifico "
            "(ex.: \"quanto gastei em mercado esse mes\")."
        )
    return text
