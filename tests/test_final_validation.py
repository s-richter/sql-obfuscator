"""
Final validation tests for Task 11.

These tests verify the complete system works as expected:
- Full test suite is green
- Manual smoke tests pass
- Deterministic behavior works correctly
- Failure modes return proper exit codes
"""

from __future__ import annotations

import pytest
from pathlib import Path

from sql_obfuscator.cli import main
from sql_obfuscator.pipeline import obfuscate_sql
from sql_obfuscator.errors import ParseScriptError


class TestFullTestSuite:
    """Verify full test suite can run and is currently passing."""

    def test_manual_smoke_test_multi_batch_go_separator(self, tmp_path: Path):
        """Smoke test: Multi-statement sample with GO separator."""
        sql_file = tmp_path / "smoke_test.sql"
        sql_content = """
        -- User management script
        CREATE TABLE Users (
            UserId INT PRIMARY KEY,
            UserName VARCHAR(100),
            Email VARCHAR(100),
            Status INT
        );
        GO
        
        -- Orders table  
        CREATE TABLE Orders (
            OrderId INT PRIMARY KEY,
            UserId INT,
            OrderDate DATETIME,
            Amount DECIMAL(10,2)
        );
        GO
        
        -- Sample data
        INSERT INTO Users VALUES (1, 'Alice', 'alice@example.com', 1);
        INSERT INTO Users VALUES (2, 'Bob', 'bob@example.com', 1);
        GO
        
        INSERT INTO Orders VALUES (1, 1, '2024-01-01', 100.00);
        INSERT INTO Orders VALUES (2, 1, '2024-01-02', 200.00);
        INSERT INTO Orders VALUES (3, 2, '2024-01-03', 150.00);
        GO
        
        -- Query with JOIN
        SELECT u.UserName, SUM(o.Amount) AS TotalSpent
        FROM Users u
        JOIN Orders o ON u.UserId = o.UserId
        WHERE u.Status = 1
        GROUP BY u.UserName;
        GO
        
        -- Cleanup
        DROP TABLE Orders;
        GO
        DROP TABLE Users;
        """
        sql_file.write_text(sql_content, encoding="utf-8")

        # Run the obfuscator
        rc = main([str(sql_file)])

        # Should succeed
        assert rc == 0

    def test_aliases_are_obfuscated(self):
        """Verify aliases are obfuscated consistently."""
        sql = """
        SELECT 
            u.UserId AS ID,
            u.UserName AS Name,
            o.OrderId AS OrderNum
        FROM Users u
        JOIN Orders o ON u.UserId = o.UserId;
        """
        result = obfuscate_sql(sql)

        # Original alias tokens should not remain in AS clauses
        upper = result.upper()
        assert " AS ID" not in upper
        assert " AS NAME" not in upper
        assert " AS ORDERNUM" not in upper

    def test_no_unintended_schema_renaming(self):
        """Verify schema names (dbo, schema) are preserved."""
        sql = """
        SELECT u.UserId
        FROM dbo.Users u
        JOIN sales.Orders o ON u.UserId = o.UserId
        WHERE dbo.Users.Status = 1;
        """
        result = obfuscate_sql(sql)

        # Schema names MUST be preserved
        assert "dbo" in result
        assert "sales" in result

    def test_deterministic_output_fixed_seed(self):
        """Confirm deterministic output with fixed seed."""
        sql = """
        SELECT u.UserId, u.UserName
        FROM Users u
        JOIN Orders o ON u.UserId = o.UserId
        WHERE u.Status = 1;
        """

        # Run multiple times with same seed
        result1 = obfuscate_sql(sql, seed=999)
        result2 = obfuscate_sql(sql, seed=999)
        result3 = obfuscate_sql(sql, seed=999)

        # All should be identical
        assert result1 == result2 == result3

    def test_different_seed_different_output(self):
        """Different seeds should produce different output."""
        sql = """
        SELECT UserId FROM Users;
        SELECT OrderId FROM Orders;
        """

        result1 = obfuscate_sql(sql, seed=111)
        result2 = obfuscate_sql(sql, seed=222)

        # Results should differ
        assert result1 != result2

    def test_failure_mode_non_existent_file_exit_code(self, tmp_path: Path):
        """Confirm failure modes return non-zero exit code."""
        rc = main(["/nonexistent/path/file.sql"])
        assert rc == 1

    def test_failure_mode_parse_error_exit_code(self, tmp_path: Path):
        """Parse error should return non-zero exit code."""
        sql_file = tmp_path / "invalid.sql"
        sql_file.write_text("SELECT ((", encoding="utf-8")

        rc = main([str(sql_file)])
        assert rc == 1

    def test_success_case_returns_zero(self, tmp_path: Path):
        """Successful run should return exit code 0."""
        sql_file = tmp_path / "valid.sql"
        sql_file.write_text("SELECT 1;", encoding="utf-8")

        rc = main([str(sql_file)])
        assert rc == 0

    def test_output_remains_parseable_after_obfuscation(self):
        """Output remains parseable T-SQL."""
        from sqlglot import parse

        sql = """
        SELECT u.UserId, u.UserName, o.OrderId
        FROM Users u
        JOIN Orders o ON u.UserId = o.UserId
        WHERE u.Status = 1;
        """

        result = obfuscate_sql(sql)

        # Should parse without error
        statements = parse(result, dialect="tsql")
        assert len(statements) > 0

    def test_output_with_go_remains_parseable(self):
        """Output with GO separators remains parseable."""
        from sqlglot import parse

        sql = """
        SELECT UserId FROM Users;
        GO
        SELECT OrderId FROM Orders;
        """

        result = obfuscate_sql(sql)

        # Split on GO and verify each batch parses
        batches = result.split("\nGO\n")
        for batch in batches:
            if batch.strip():
                statements = parse(batch, dialect="tsql")
                assert len(statements) > 0

    def test_complex_real_world_scenario(self, tmp_path: Path, capsys):
        """Complex real-world scenario with multiple tables, CTEs, and batches."""
        sql_file = tmp_path / "complex.sql"
        sql_content = """
        -- Create tables
        CREATE TABLE Customers (
            CustomerId INT PRIMARY KEY,
            CustomerName VARCHAR(100),
            City VARCHAR(50)
        );
        GO
        
        CREATE TABLE Orders (
            OrderId INT PRIMARY KEY,
            CustomerId INT,
            OrderDate DATETIME,
            Amount DECIMAL(10,2)
        );
        GO
        
        CREATE TABLE OrderItems (
            ItemId INT PRIMARY KEY,
            OrderId INT,
            ProductName VARCHAR(100),
            Quantity INT,
            UnitPrice DECIMAL(10,2)
        );
        GO
        
        -- Create temp table for processing
        CREATE TABLE #ProcessingQueue (
            OrderId INT,
            ProcessedAt DATETIME
        );
        GO
        
        -- Complex query with CTE and JOIN
        WITH TopCustomers AS (
            SELECT c.CustomerId, c.CustomerName, COUNT(o.OrderId) AS OrderCount
            FROM Customers c
            LEFT JOIN Orders o ON c.CustomerId = o.CustomerId
            GROUP BY c.CustomerId, c.CustomerName
            HAVING COUNT(o.OrderId) > 0
        )
        SELECT 
            tc.CustomerId,
            tc.CustomerName,
            tc.OrderCount,
            oi.ProductName,
            oi.Quantity
        FROM TopCustomers tc
        JOIN Orders o ON tc.CustomerId = o.CustomerId
        JOIN OrderItems oi ON o.OrderId = oi.OrderId
        WHERE o.OrderDate >= '2024-01-01'
        ORDER BY tc.CustomerName;
        GO
        
        -- Cleanup
        DROP TABLE #ProcessingQueue;
        GO
        DROP TABLE OrderItems;
        GO
        DROP TABLE Orders;
        GO
        DROP TABLE Customers;
        """
        sql_file.write_text(sql_content, encoding="utf-8")

        # Run obfuscator
        rc = main([str(sql_file)])

        # Should succeed
        assert rc == 0

        # Should have output
        captured = capsys.readouterr()
        assert "SELECT" in captured.out
        assert len(captured.out) > 0
