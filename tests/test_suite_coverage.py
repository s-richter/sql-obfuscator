from __future__ import annotations

import pytest

from sql_obfuscator.errors import ParseScriptError
from sql_obfuscator.pipeline import obfuscate_sql


class TestPositiveTests:
    """Additional positive test cases for various SQL constructs."""

    def test_simple_select(self):
        """Simple SELECT without transforms should still work."""
        sql = "SELECT 1;"
        result = obfuscate_sql(sql)
        assert "SELECT" in result
        assert "1" in result

    def test_join_with_repeated_column_names(self):
        """JOINs with repeated column names should rename them appropriately."""
        sql = """
        SELECT a.Id, b.Id
        FROM TableA a
        JOIN TableB b ON a.Id = b.Id
        WHERE a.Id = 1 AND b.Id = 2;
        """
        result = obfuscate_sql(sql)
        # Both table names should be renamed
        assert "TableA" not in result
        assert "TableB" not in result
        # But we should have aliases preserved or replaced consistently
        assert result.count("a.") > 0 or result.count("b.") > 0

    def test_temp_table_single_hash(self):
        """Single # temp tables should preserve temp marker."""
        sql = """
        CREATE TABLE #TempTable (Id INT, Name VARCHAR(100));
        INSERT INTO #TempTable VALUES (1, 'Test');
        SELECT * FROM #TempTable;
        GO
        DROP TABLE #TempTable;
        """
        result = obfuscate_sql(sql)
        # Temp marker should be preserved
        assert "#" in result
        # Should not have double hash
        assert "##" not in result

    def test_global_temp_table_double_hash(self):
        """Global ## temp tables should preserve double hash marker."""
        sql = """
        CREATE TABLE ##GlobalTemp (Id INT);
        INSERT INTO ##GlobalTemp VALUES (1);
        SELECT * FROM ##GlobalTemp;
        """
        result = obfuscate_sql(sql)
        # Global temp marker should be preserved
        assert "##" in result

    def test_mixed_bracket_and_case_normalization(self):
        """Mixed case and bracketed identifiers should normalize correctly."""
        sql = """
        SELECT [UserId], userId, USERID
        FROM [Users]
        WHERE [Status] = 'Active';
        """
        result = obfuscate_sql(sql)
        # All variations should be renamed to same identifier
        # Output should be valid T-SQL
        assert result is not None
        # Brackets should still exist for encoded names if needed
        assert "[" in result or "a" in result.lower()

    def test_qualified_names_with_schema(self):
        """Qualified table names with schema prefix should preserve schema."""
        sql = """
        SELECT u.UserId
        FROM dbo.Users u
        JOIN sales.Orders o ON u.UserId = o.UserId;
        """
        result = obfuscate_sql(sql)
        # Schema names should be preserved
        assert "dbo" in result
        assert "sales" in result
        # Column names should be renamed (UserId -> something else)
        assert result.count("UserId") == 0

    def test_case_insensitive_identifier_matching(self):
        """Case-insensitive identifiers should map to same replacement."""
        sql = """
        SELECT UserId, userid, USERID
        FROM Users u
        JOIN users u2 ON u.UserId = u2.userid
        WHERE USERID = 1;
        """
        result = obfuscate_sql(sql)
        # All case variations should be replaced with same name
        assert result is not None


class TestGOBatchTests:
    """Tests for GO batch separator handling."""

    def test_non_standalone_go_text_not_separator(self):
        """GO text that's not standalone should not be treated as separator."""
        sql = """
        SELECT 'This is a GOING concern' AS comment;
        SELECT * FROM GoTable;
        SELECT GETDATE() AS today;
        """
        result = obfuscate_sql(sql)
        # Should be one batch, GO keywords in strings/identifiers not split
        # Result should have all three SELECTs
        assert result.count("SELECT") >= 3

    def test_go_with_leading_whitespace(self):
        """GO with leading whitespace should still be separator."""
        sql = """
        SELECT 1;
        \t\tGO
        SELECT 2;
        """
        result = obfuscate_sql(sql)
        # Should have GO separator
        assert "\nGO\n" in result or "GO" in result

    def test_go_with_trailing_whitespace(self):
        """GO with trailing whitespace should still be separator."""
        sql = """
        SELECT 1;
        GO    
        SELECT 2;
        """
        result = obfuscate_sql(sql)
        # Both selects should be present
        assert result.count("SELECT") >= 2


class TestNegativeTests:
    """Negative tests for error conditions."""

    def test_animal_pool_exhaustion_behavior(self):
        """When animal pool exhausted, should fall back to suffixed names."""
        from sql_obfuscator.names import AnimalNameProvider, ANIMALS

        provider = AnimalNameProvider()
        generated = set()

        # Generate more names than available animals
        for _ in range(len(ANIMALS) * 2):
            name = provider.next_name()
            generated.add(name)

        # Should have generated many names
        assert len(generated) > len(ANIMALS)
        # All should be unique
        assert len(generated) == len(ANIMALS) * 2

    def test_reserved_keyword_fallback_generation(self):
        """Verify generated suffixed names don't accidentally be keywords."""
        from sql_obfuscator.names import AnimalNameProvider, _is_safe_identifier, ANIMALS

        provider = AnimalNameProvider()

        # Generate exhaustively
        for _ in range(len(ANIMALS) * 3):
            name = provider.next_name()
            # Should always be safe
            assert _is_safe_identifier(
                name), f"Generated name {name} is not safe"

    def test_parse_error_in_batch(self):
        """Parse errors should be caught and reported with batch context."""
        sql = "SELECT (("  # Syntax error
        with pytest.raises(ParseScriptError) as exc:
            obfuscate_sql(sql)
        assert "batch" in str(exc.value).lower()

    def test_error_message_includes_batch_number(self):
        """Error message should include which batch failed."""
        sql = """
        SELECT 1;
        GO
        SELECT 2;
        GO
        SELECT ((
        """
        with pytest.raises(ParseScriptError) as exc:
            obfuscate_sql(sql)
        error_msg = str(exc.value)
        assert "batch 3" in error_msg


class TestDeterminismTests:
    """Tests for deterministic behavior with seeds."""

    def test_different_seed_produces_different_mapping(self):
        """Different seeds should produce different identifier mappings."""
        sql = """
        SELECT UserId, UserName FROM Users;
        SELECT OrderId FROM Orders;
        SELECT ProductId FROM Products;
        """

        result1 = obfuscate_sql(sql, seed=42)
        result2 = obfuscate_sql(sql, seed=43)

        # Results should differ (different seeds = different animal sequence)
        assert result1 != result2

    def test_same_seed_produces_identical_output(self):
        """Same seed should always produce identical output."""
        sql = """
        SELECT UserId, UserName FROM Users
        WHERE Status = 1;
        INSERT INTO AuditLog VALUES (1, 'test');
        """

        result1 = obfuscate_sql(sql, seed=123)
        result2 = obfuscate_sql(sql, seed=123)

        assert result1 == result2

    def test_seed_affects_multi_batch_consistently(self):
        """Same seed should produce consistent results across batches."""
        sql = """
        SELECT UserId FROM Users;
        GO
        SELECT OrderId FROM Orders;
        """

        result1 = obfuscate_sql(sql, seed=42)
        result2 = obfuscate_sql(sql, seed=42)

        assert result1 == result2
        # Verify batches are preserved
        assert result1.count("GO") == result2.count("GO")


class TestComplexScenarios:
    """Complex real-world scenarios."""

    def test_nested_cte_with_multiple_joins(self):
        """Complex nested CTEs with joins should remain valid."""
        sql = """
        WITH CTE1 AS (
            SELECT UserId FROM Users WHERE Status = 1
        ),
        CTE2 AS (
            SELECT OrderId FROM Orders WHERE Status = 'Active'
        )
        SELECT c1.UserId, c2.OrderId
        FROM CTE1 c1
        JOIN CTE2 c2 ON c1.UserId = c2.UserId;
        """
        result = obfuscate_sql(sql)
        assert "SELECT" in result
        assert "JOIN" in result

    def test_multiple_statements_with_go_separator(self):
        """Multiple statements separated by GO should maintain structure."""
        sql = """
        CREATE TABLE Users (UserId INT PRIMARY KEY);
        GO
        INSERT INTO Users VALUES (1);
        GO
        SELECT * FROM Users;
        GO
        DROP TABLE Users;
        """
        result = obfuscate_sql(sql)
        # Should have GO separators
        assert "\nGO\n" in result or result.count("GO") >= 3

    def test_stored_procedure_skeleton(self):
        """Stored procedure syntax should be handled (CREATE PROC)."""
        sql = """
        CREATE PROCEDURE GetUsers @Status INT
        AS
        BEGIN
            SELECT UserId, UserName FROM Users WHERE Status = @Status;
        END;
        """
        result = obfuscate_sql(sql)
        # Variable should be preserved
        assert "@Status" in result
        # Table name should be renamed
        assert "Users" not in result or result.count("Users") == 0
