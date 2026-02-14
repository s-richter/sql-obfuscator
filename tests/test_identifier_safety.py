from __future__ import annotations

import pytest
from sqlglot import parse

from sql_obfuscator.names import (
    TSQL_RESERVED_KEYWORDS,
    bracket_if_needed,
    _is_safe_identifier,
)
from sql_obfuscator.pipeline import obfuscate_sql


class TestBracketingAndSafety:
    def test_bracket_if_needed_safe_identifier_not_bracketed(self):
        """Safe identifiers should not be bracketed."""
        assert bracket_if_needed("shark") == "shark"
        assert bracket_if_needed("_temp_table") == "_temp_table"
        assert bracket_if_needed("User123") == "User123"

    def test_bracket_if_needed_keyword_gets_bracketed(self):
        """Reserved keywords should be bracketed."""
        assert bracket_if_needed("select") == "[select]"
        assert bracket_if_needed("SELECT") == "[SELECT]"
        assert bracket_if_needed("from") == "[from]"

    def test_bracket_if_needed_escapes_brackets(self):
        """Brackets in value should be doubled."""
        assert bracket_if_needed("a]b") == "[a]]b]"
        assert bracket_if_needed("[test]") == "[[test]]]"

    def test_bracket_if_needed_special_chars_get_bracketed(self):
        """Identifiers with special chars should be bracketed."""
        assert bracket_if_needed("my-table") == "[my-table]"
        assert bracket_if_needed("table name") == "[table name]"
        assert bracket_if_needed("123invalid") == "[123invalid]"

    def test_is_safe_identifier_rejects_keywords(self):
        """All reserved keywords should be rejected."""
        for keyword in ["select", "from", "where", "insert", "update"]:
            assert not _is_safe_identifier(keyword)
            assert not _is_safe_identifier(keyword.upper())

    def test_is_safe_identifier_accepts_safe_names(self):
        """Valid non-keyword names should be accepted."""
        assert _is_safe_identifier("shark")
        assert _is_safe_identifier("dolphin")
        assert _is_safe_identifier("_private")
        assert _is_safe_identifier("Table1")

    def test_is_safe_identifier_rejects_invalid_syntax(self):
        """Invalid identifier syntax should be rejected."""
        assert not _is_safe_identifier("")
        assert not _is_safe_identifier("123start")
        assert not _is_safe_identifier("my-table")
        assert not _is_safe_identifier("my table")
        assert not _is_safe_identifier("my.table")


class TestOutputParseability:
    def test_obfuscated_output_is_parseable(self):
        """Transformed SQL should remain parseable."""
        sql = """
        SELECT UserId, UserName 
        FROM Users 
        WHERE Status = 'Active';
        """
        result = obfuscate_sql(sql)
        # Should not raise parse error
        statements = parse(result, dialect="tsql")
        assert len(statements) > 0

    def test_obfuscated_multi_batch_is_parseable(self):
        """Multi-batch transformed SQL should be parseable."""
        sql = """
        SELECT UserId FROM Users;
        GO
        INSERT INTO Audit VALUES (1, 'test');
        GO
        UPDATE Users SET Status = 1 WHERE UserId = 5;
        """
        result = obfuscate_sql(sql)
        # Should be able to split and parse each batch
        batches = result.split("\nGO\n")
        for batch in batches:
            if batch.strip():
                statements = parse(batch, dialect="tsql")
                assert len(statements) > 0

    def test_obfuscated_cte_is_parseable(self):
        """CTEs should remain parseable after obfuscation."""
        sql = """
        WITH UserCTE AS (
            SELECT UserId, UserName FROM Users
        )
        SELECT * FROM UserCTE;
        """
        result = obfuscate_sql(sql)
        statements = parse(result, dialect="tsql")
        assert len(statements) > 0

    def test_obfuscated_joins_remain_parseable(self):
        """JOINs should remain parseable after obfuscation."""
        sql = """
        SELECT u.UserId, o.OrderId
        FROM Users u
        JOIN Orders o ON u.UserId = o.UserId
        WHERE u.Status = 1;
        """
        result = obfuscate_sql(sql)
        statements = parse(result, dialect="tsql")
        assert len(statements) > 0

    def test_obfuscated_temp_tables_are_parseable(self):
        """Temp tables should remain parseable after obfuscation."""
        sql = """
        CREATE TABLE #TempUsers (UserId INT, UserName VARCHAR(100));
        INSERT INTO #TempUsers VALUES (1, 'Alice');
        SELECT * FROM #TempUsers;
        GO
        DROP TABLE #TempUsers;
        """
        result = obfuscate_sql(sql)
        batches = result.split("\nGO\n")
        for batch in batches:
            if batch.strip():
                statements = parse(batch, dialect="tsql")
                assert len(statements) > 0

    def test_obfuscated_global_temp_tables_are_parseable(self):
        """Global temp tables (##) should remain parseable."""
        sql = """
        CREATE TABLE ##GlobalTemp (Id INT);
        INSERT INTO ##GlobalTemp VALUES (1);
        """
        result = obfuscate_sql(sql)
        statements = parse(result, dialect="tsql")
        assert len(statements) > 0


class TestNoReservedKeywordCollisions:
    def test_generated_names_are_safe(self):
        """All generated names should be safe (not keywords)."""
        from sql_obfuscator.names import AnimalNameProvider

        provider = AnimalNameProvider()
        for _ in range(100):
            name = provider.next_name()
            assert _is_safe_identifier(
                name), f"Generated name {name} is not safe"

    def test_generated_suffixed_names_are_safe(self):
        """Even suffixed fallback names should be safe."""
        from sql_obfuscator.names import AnimalNameProvider, ANIMALS

        provider = AnimalNameProvider()
        # Exhaust the animal list multiple times to force suffixed names
        for _ in range(len(ANIMALS) * 3):
            name = provider.next_name()
            assert _is_safe_identifier(
                name
            ), f"Generated suffixed name {name} is not safe"

    def test_deterministic_generation_consistent(self):
        """Same seed should produce same sequence of names."""
        from sql_obfuscator.names import AnimalNameProvider

        provider1 = AnimalNameProvider(seed=42)
        provider2 = AnimalNameProvider(seed=42)

        for _ in range(50):
            assert provider1.next_name() == provider2.next_name()

    def test_different_seeds_produce_different_sequences(self):
        """Different seeds should produce different name sequences."""
        from sql_obfuscator.names import AnimalNameProvider

        provider1 = AnimalNameProvider(seed=42)
        provider2 = AnimalNameProvider(seed=43)

        names1 = [provider1.next_name() for _ in range(10)]
        names2 = [provider2.next_name() for _ in range(10)]

        # Sequences should differ (statistically very likely)
        assert names1 != names2


class TestOutputSyntacticValidity:
    def test_qualified_names_remain_valid(self):
        """Qualified names (schema.table) should remain valid."""
        sql = """
        SELECT u.UserId, u.UserName
        FROM dbo.Users u
        WHERE dbo.Users.Status = 1;
        """
        result = obfuscate_sql(sql)
        # dbo schema prefix should be preserved; output should parse
        statements = parse(result, dialect="tsql")
        assert len(statements) > 0
        # Verify dbo is still in output
        assert "dbo" in result

    def test_column_aliases_obfuscated(self):
        """Column aliases should be obfuscated consistently."""
        sql = """
        SELECT UserId AS ID, UserName AS Name
        FROM Users;
        """
        result = obfuscate_sql(sql)
        # Aliases should be obfuscated, not kept as original tokens
        assert "ID" not in result.upper() and "NAME" not in result.upper()
        statements = parse(result, dialect="tsql")
        assert len(statements) > 0

    def test_string_literals_unchanged(self):
        """String literals should not be affected."""
        sql = """
        SELECT UserId
        FROM Users
        WHERE Status = 'Active';
        """
        result = obfuscate_sql(sql)
        # String literal should be preserved
        assert "'Active'" in result
        statements = parse(result, dialect="tsql")
        assert len(statements) > 0

    def test_variables_not_renamed(self):
        """Variables (@var) should not be renamed."""
        sql = """
        DECLARE @UserId INT = 1;
        SELECT * FROM Users WHERE UserId = @UserId;
        """
        result = obfuscate_sql(sql)
        # Variable should be preserved
        assert "@UserId" in result
        statements = parse(result, dialect="tsql")
        assert len(statements) > 0
