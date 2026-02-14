from sql_obfuscator.registry import IdentifierRegistry, normalize_identifier


def test_normalize_identifier_brackets_case():
    assert normalize_identifier("[UserId]") == normalize_identifier("userid")


def test_normalize_identifier_temp_prefix():
    assert normalize_identifier("#Temp").temp_prefix == "#"
    assert normalize_identifier("##Temp").temp_prefix == "##"


def test_registry_deterministic_seed():
    a = IdentifierRegistry(seed=7)
    b = IdentifierRegistry(seed=7)
    assert a.get_or_create("Users") == b.get_or_create("Users")
    assert a.get_or_create("[UserId]") == b.get_or_create("userid")
