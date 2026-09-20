from app.services.fuzzy_match import fuzzy_find_one


def test_fuzzy_find_one_typo():
    assert fuzzy_find_one("Nubanck", ["Nubank", "Itaú", "Caixa"]) == "Nubank"


def test_fuzzy_find_one_exact():
    assert fuzzy_find_one("Nubank", ["Nubank", "Itaú"]) == "Nubank"


def test_fuzzy_find_one_case_insensitive():
    assert fuzzy_find_one("nubank", ["Nubank"]) == "Nubank"


def test_fuzzy_find_one_empty_candidates():
    assert fuzzy_find_one("Nubank", []) is None


def test_fuzzy_find_one_empty_query():
    assert fuzzy_find_one("", ["Nubank"]) is None
    assert fuzzy_find_one("   ", ["Nubank"]) is None


def test_fuzzy_find_one_below_cutoff_returns_none():
    assert fuzzy_find_one("Nubank", ["Itaú"]) is None
    assert fuzzy_find_one("Xyz", ["Nubank", "Itaú", "Caixa"]) is None


def test_fuzzy_find_one_ignores_missing_accent():
    assert fuzzy_find_one("Itau", ["Nubank", "Itaú", "Caixa", "Inter"]) == "Itaú"


def test_fuzzy_find_one_does_not_confuse_different_banks():
    assert fuzzy_find_one("Nubank", ["Itaú", "Caixa", "Inter", "Bradesco"]) is None
