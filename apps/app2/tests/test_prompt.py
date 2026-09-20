import json

from app.agent.prompt import SYSTEM_PROMPT, extract_json


def test_system_prompt_has_few_shot_examples():
    assert "Exemplos" in SYSTEM_PROMPT
    example_lines = [
        line
        for line in SYSTEM_PROMPT.splitlines()
        if line.strip().startswith("-") and '"tool"' in line
    ]
    assert len(example_lines) >= 6


def test_system_prompt_examples_are_valid_json():
    for line in SYSTEM_PROMPT.splitlines():
        stripped = line.strip()
        if not stripped.startswith("-") or "->" not in stripped:
            continue
        _, _, json_part = stripped.partition("->")
        payload = extract_json(json_part.strip())
        assert payload is not None, f"exemplo invalido: {line}"
        assert "tool" in payload and "arguments" in payload
        json.loads(json.dumps(payload))
