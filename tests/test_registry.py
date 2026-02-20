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


def test_registry_mapping_payload_includes_occurrences():
    registry = IdentifierRegistry(seed=7)
    registry.get_or_create(
        "Users",
        kind="table",
        batch_index=1,
        statement_index=1,
        scope_id="b1.s1.table.this",
        parent_kind="select",
        role="table_reference",
    )
    payload = registry.mapping_payload()

    assert payload["schema_version"] == 1
    assert len(payload["entries"]) == 1
    assert "forward_index" in payload
    assert "reverse_index" in payload
    entry = payload["entries"][0]
    assert entry["normalized_original"] == "users"
    assert entry["original_lexeme"] == "Users"
    assert len(entry["occurrences"]) == 1
    assert entry["occurrences"][0]["kind"] == "table"
    assert payload["forward_index"]["users"] == entry["obfuscated_lexeme"]
    assert payload["reverse_index"][entry["obfuscated_lexeme"]]["normalized_original"] == "users"


def test_registry_occurrence_includes_optional_type_lexeme():
    registry = IdentifierRegistry(seed=7)
    registry.get_or_create(
        "OrderTotal",
        kind="column_def",
        batch_index=1,
        statement_index=1,
        scope_id="b1.s1.columndef.expressions",
        parent_kind="schema",
        role="column_definition",
        type_lexeme="DECIMAL",
    )
    payload = registry.mapping_payload()
    occurrence = payload["entries"][0]["occurrences"][0]
    assert occurrence["type_lexeme"] == "DECIMAL"
