"""O toolkit é reenviado em toda iteração do loop: payload enxuto é requisito.

O tier free do Groq limita a 8.000 tokens/min; com o JSON Schema cru do pydantic
(o toolkit todo passava de 6.000 tokens por chamada) o agente v2 tomava 429 já
na primeira iteração. Estes testes travam o teto e garantem que a compactação não
perde informação que o modelo precisa (tipo, enum, formato, limites).
"""
import json

from app.agent.toolkit import build_toolkit, compact_schema, openai_tools, validate_write

MAX_PAYLOAD_CHARS = 17_000


def _walk(node):
    if isinstance(node, list):
        for item in node:
            yield from _walk(item)
    elif isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)


def test_toolkit_payload_dentro_do_teto():
    payload = json.dumps(openai_tools(build_toolkit()), ensure_ascii=False)
    assert len(payload) < MAX_PAYLOAD_CHARS, (
        f"toolkit com {len(payload)} chars (~{len(payload) // 4} tokens); "
        f"teto {MAX_PAYLOAD_CHARS}"
    )


def test_sem_titulo_nem_anyof_com_null():
    for node in _walk(openai_tools(build_toolkit())):
        assert "title" not in node
        branches = node.get("anyOf")
        if isinstance(branches, list):
            assert not any(b.get("type") == "null" for b in branches if isinstance(b, dict))


def test_tipo_enum_formato_e_limites_preservados():
    tool = build_toolkit()["register_expense"].to_openai_tool()
    props = tool["function"]["parameters"]["properties"]

    assert props["installment_count"] == {
        "type": "integer",
        "minimum": 2,
        "maximum": 360,
    }
    assert props["status"] == {
        "type": "string",
        "enum": ["actual", "planned"],
        "default": "actual",
    }
    assert props["competence_date"] == {"type": "string", "format": "date"}
    assert props["amount"] == {"type": "string"}


def test_opcionais_continuam_fora_do_required():
    params = build_toolkit()["register_expense"].to_openai_tool()["function"]["parameters"]
    assert params["required"] == ["amount", "description"]
    assert "installment_count" in params["properties"]


def test_validacao_de_escrita_inalterada():
    spec = build_toolkit()["register_expense"]
    valid = validate_write(spec, {"amount": "35.50", "description": "Mercado"})
    assert valid["amount"] == "35.50"


def test_compact_schema_preserva_qualquer_no():
    schema = {
        "type": "object",
        "properties": {"x": {"title": "X", "anyOf": [{"type": "string"}, {"type": "null"}]}},
        "required": [],
    }
    assert compact_schema(schema) == {
        "type": "object",
        "properties": {"x": {"type": "string"}},
        "required": [],
    }