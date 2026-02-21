from __future__ import annotations

import json
from pathlib import Path

from sql_obfuscator.cli import main


def test_llm_style_edited_obfuscated_sql_deobfuscates_cleanly(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text(
        """
        SELECT u.UserId, o.OrderId
        FROM Users u
        JOIN Orders o ON u.UserId = o.UserId
        WHERE u.Status = 1;
        """,
        encoding="utf-8",
    )
    workspace = tmp_path / "input.obf"

    assert main(["obfuscate", str(sql_file), "--workspace", str(workspace), "--seed", "123"]) == 0
    capsys.readouterr()

    obfuscated_sql = (workspace / "obfuscated.sql").read_text(encoding="utf-8")
    # Simulate a realistic LLM rewrite that preserves identifier tokens.
    edited_obfuscated = obfuscated_sql.replace("WHERE", "WHERE 1 = 1 AND", 1)
    edited_path = workspace / "llm_response_obfuscated.sql"
    edited_path.write_text(edited_obfuscated, encoding="utf-8")

    rc = main(
        [
            "deobfuscate",
            "--workspace",
            str(workspace),
            "--input",
            str(edited_path),
        ]
    )
    capsys.readouterr()

    assert rc == 0
    report = json.loads((workspace / "reports" / "deobfuscation_report.json").read_text(encoding="utf-8"))
    assert report["unknown_count"] == 0
    assert report["ambiguous_count"] == 0
    deobfuscated_sql = (workspace / "deobfuscated.sql").read_text(encoding="utf-8")
    assert "Users" in deobfuscated_sql
    assert "Orders" in deobfuscated_sql
    assert "1 = 1" in deobfuscated_sql


def test_llm_style_edit_multi_batch_dry_run_clean(tmp_path: Path, capsys):
    sql_file = tmp_path / "multi.sql"
    sql_file.write_text(
        """
        SELECT UserId FROM Users;
        GO
        SELECT OrderId FROM Orders WHERE OrderId > 0;
        """,
        encoding="utf-8",
    )
    workspace = tmp_path / "multi.obf"

    assert main(["obfuscate", str(sql_file), "--workspace", str(workspace), "--seed", "99"]) == 0
    capsys.readouterr()

    obfuscated_sql = (workspace / "obfuscated.sql").read_text(encoding="utf-8")
    edited_obfuscated = obfuscated_sql.replace("SELECT", "SELECT DISTINCT", 1)
    edited_path = workspace / "llm_response_obfuscated.sql"
    edited_path.write_text(edited_obfuscated, encoding="utf-8")

    rc = main(
        [
            "deobfuscate",
            "--workspace",
            str(workspace),
            "--input",
            str(edited_path),
            "--dry-run",
        ]
    )
    captured = capsys.readouterr()

    assert rc == 0
    assert "unknown_count: 0" in captured.out
    assert "ambiguous_count: 0" in captured.out


def test_saved_mapping_artifacts_are_reproducible_with_same_seed(tmp_path: Path, capsys):
    sql_file = tmp_path / "seeded.sql"
    sql_file.write_text(
        "SELECT UserId, UserName FROM Users WHERE Status = 1;",
        encoding="utf-8",
    )
    ws1 = tmp_path / "ws1"
    ws2 = tmp_path / "ws2"

    assert main(["obfuscate", str(sql_file), "--workspace", str(ws1), "--seed", "42"]) == 0
    capsys.readouterr()
    assert main(["obfuscate", str(sql_file), "--workspace", str(ws2), "--seed", "42"]) == 0
    capsys.readouterr()

    mapping1 = json.loads((ws1 / "mapping.json").read_text(encoding="utf-8"))
    mapping2 = json.loads((ws2 / "mapping.json").read_text(encoding="utf-8"))
    context1 = json.loads((ws1 / "context.json").read_text(encoding="utf-8"))
    context2 = json.loads((ws2 / "context.json").read_text(encoding="utf-8"))
    obf1 = (ws1 / "obfuscated.sql").read_text(encoding="utf-8")
    obf2 = (ws2 / "obfuscated.sql").read_text(encoding="utf-8")

    assert mapping1 == mapping2
    assert context1 == context2
    assert obf1 == obf2


def test_saved_mapping_artifacts_change_with_different_seed(tmp_path: Path, capsys):
    sql_file = tmp_path / "seeded.sql"
    sql_file.write_text(
        "SELECT UserId, UserName FROM Users WHERE Status = 1;",
        encoding="utf-8",
    )
    ws1 = tmp_path / "ws1"
    ws2 = tmp_path / "ws2"

    assert main(["obfuscate", str(sql_file), "--workspace", str(ws1), "--seed", "41"]) == 0
    capsys.readouterr()
    assert main(["obfuscate", str(sql_file), "--workspace", str(ws2), "--seed", "42"]) == 0
    capsys.readouterr()

    mapping1 = json.loads((ws1 / "mapping.json").read_text(encoding="utf-8"))
    mapping2 = json.loads((ws2 / "mapping.json").read_text(encoding="utf-8"))
    obf1 = (ws1 / "obfuscated.sql").read_text(encoding="utf-8")
    obf2 = (ws2 / "obfuscated.sql").read_text(encoding="utf-8")

    assert mapping1["forward_index"] != mapping2["forward_index"]
    assert obf1 != obf2


def test_obfuscate_translate_roundtrip_back_then_deobfuscate_dry_run_clean(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text(
        """
        SELECT u.UserId, o.OrderId
        FROM Users u
        JOIN Orders o ON u.UserId = o.UserId
        WHERE o.OrderId > 10;
        """,
        encoding="utf-8",
    )
    workspace = tmp_path / "input.obf"

    assert main(["obfuscate", str(sql_file), "--workspace", str(workspace), "--seed", "123"]) == 0
    capsys.readouterr()

    obfuscated_path = workspace / "obfuscated.sql"
    tsql_to_hive = tmp_path / "obf_hive.sql"
    hive_to_tsql = tmp_path / "obf_tsql.sql"

    assert (
        main(
            [
                "translate",
                "--input",
                str(obfuscated_path),
                "--source-dialect",
                "tsql",
                "--target-dialect",
                "hive",
                "--out",
                str(tsql_to_hive),
                "--validate",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "translate",
                "--input",
                str(tsql_to_hive),
                "--source-dialect",
                "hive",
                "--target-dialect",
                "tsql",
                "--out",
                str(hive_to_tsql),
                "--validate",
            ]
        )
        == 0
    )
    capsys.readouterr()

    rc = main(
        [
            "deobfuscate",
            "--workspace",
            str(workspace),
            "--input",
            str(hive_to_tsql),
            "--dry-run",
        ]
    )
    captured = capsys.readouterr()

    assert rc == 0
    assert "unknown_count: 0" in captured.out
    assert "ambiguous_count: 0" in captured.out
