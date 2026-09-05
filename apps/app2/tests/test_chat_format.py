from app.chat_format import chat_md


def test_chat_md_escapes_html():
    result = str(chat_md("<script>alert(1)</script>"))
    assert "<script>" not in result
    assert "&lt;script&gt;" in result


def test_chat_md_single_asterisk_bold():
    result = str(chat_md("Responda com *despesa* ou *receita*."))
    assert "<strong>despesa</strong>" in result
    assert "<strong>receita</strong>" in result


def test_chat_md_double_asterisk_bold():
    result = str(chat_md("Escolha **realizado** ou previsto."))
    assert "<strong>realizado</strong>" in result


def test_chat_md_list():
    result = str(chat_md("Últimas:\n- a\n- b"))
    assert "<ul class=\"chat-md-list\">" in result
    assert "<li>a</li>" in result
    assert "<li>b</li>" in result


def test_chat_md_unclosed_asterisk():
    result = str(chat_md("preço * 2"))
    assert "<strong>" not in result
    assert "preço * 2" in result


def test_chat_md_empty():
    assert str(chat_md(None)) == ""
    assert str(chat_md("")) == ""
