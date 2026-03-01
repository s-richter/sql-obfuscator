import re

from sql_obfuscator.pipeline import obfuscate_sql


def test_select_join_renames_tables_columns_and_aliases_keeps_schema():
    sql = "SELECT u.UserId, o.Id FROM dbo.Users u JOIN Orders o ON u.UserId = o.UserId"
    output = obfuscate_sql(sql, seed=1)

    assert "Users" not in output
    assert "Orders" not in output
    assert "UserId" not in output
    assert ".Id" not in output
    assert "dbo." in output
    assert " AS u " not in output
    assert " AS o " not in output


def test_cte_name_is_renamed_in_declaration_and_reference():
    sql = "WITH RecentOrders AS (SELECT UserId FROM Orders) SELECT UserId FROM RecentOrders"
    output = obfuscate_sql(sql, seed=1)

    assert "RecentOrders" not in output
    assert "WITH " in output
    assert " FROM " in output


def test_temp_table_name_and_columns_are_renamed():
    sql = "CREATE TABLE #TempOrders (UserId INT); INSERT INTO #TempOrders (UserId) VALUES (1)"
    output = obfuscate_sql(sql, seed=1)

    assert "#TempOrders" not in output
    assert "UserId" not in output
    assert "#" in output
    assert "INSERT INTO #" in output


def test_update_alias_target_is_renamed_consistently():
    sql = "UPDATE u SET u.UserId = 1 FROM Users u"
    output = obfuscate_sql(sql, seed=1, pretty=False)

    assert output.startswith("UPDATE ")
    assert output.startswith("UPDATE u ") is False
    assert "FROM " in output
    assert " AS u " not in output
    assert "UserId" not in output
    match = re.fullmatch(
        r"UPDATE (?P<alias>[A-Za-z_][A-Za-z0-9_]*) "
        r"SET (?P=alias)\.[A-Za-z_][A-Za-z0-9_]* = 1 "
        r"FROM [A-Za-z_][A-Za-z0-9_]* AS (?P=alias)",
        output,
    )
    assert match is not None, output


def test_expression_alias_is_renamed():
    sql = "SELECT SUM(o.OrderTotal) AS TotalAmount FROM Orders o"
    output = obfuscate_sql(sql, seed=1)

    assert "OrderTotal" not in output
    assert "TotalAmount" not in output


def test_keywords_literals_variables_and_functions_are_not_renamed():
    sql = "SELECT ABS(UserId), @UserId, 'Users', 100, u.UserId FROM Users u WHERE u.UserId = 1"
    output = obfuscate_sql(sql, seed=1)

    assert "ABS(" in output
    assert "@UserId" in output
    assert "'Users'" in output
    assert "100" in output
