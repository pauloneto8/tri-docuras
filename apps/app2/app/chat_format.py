"""Formatação leve de markdown para mensagens do assistente no chat."""

from __future__ import annotations

import html
import re

from markupsafe import Markup

_BOLD_DOUBLE = re.compile(r"\*\*(.+?)\*\*")
_BOLD_SINGLE = re.compile(r"\*(.+?)\*")


def chat_md(text: str | None) -> Markup:
    if text is None or text == "":
        return Markup("")

    escaped = html.escape(text)
    escaped = _BOLD_DOUBLE.sub(r"<strong>\1</strong>", escaped)
    escaped = _BOLD_SINGLE.sub(r"<strong>\1</strong>", escaped)

    blocks = re.split(r"\n\n+", escaped)
    html_blocks: list[str] = []

    for block in blocks:
        lines = block.split("\n")
        parts: list[str] = []
        list_items: list[str] = []

        def flush_list() -> None:
            if list_items:
                items = "".join(f"<li>{item}</li>" for item in list_items)
                parts.append(f'<ul class="chat-md-list">{items}</ul>')
                list_items.clear()

        for line in lines:
            if line.startswith("- "):
                list_items.append(line[2:])
            else:
                flush_list()
                if line.strip():
                    parts.append(line)
        flush_list()

        if parts:
            html_blocks.append("<br>".join(parts))

    return Markup("<br><br>".join(html_blocks))
