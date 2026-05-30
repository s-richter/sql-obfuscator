from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from sql_obfuscator.cli import main


def test_cli_missing_file_returns_nonzero(capsys):
    rc = main(["obfuscate", "does_not_exist.sql"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "Error:" in captured.err


def test_cli_prints_output_for_valid_sql(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT 1;", encoding="utf-8")

    rc = main(["obfuscate", str(sql_file)])
    captured = capsys.readouterr()

    assert rc == 0
    assert "SELECT" in captured.out
    assert "1" in captured.out


def test_cli_writes_obfuscated_output_file(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT 1;", encoding="utf-8")

    rc = main(["obfuscate", str(sql_file)])
    capsys.readouterr()

    output_file = tmp_path / "input_obfuscated.sql"
    assert rc == 0
    assert output_file.exists()
    output = output_file.read_text(encoding="utf-8")
    assert "SELECT" in output
    assert "1" in output
    workspace_dir = tmp_path / "input.obf"
    assert workspace_dir.exists()
    assert (workspace_dir / "original.sql").exists()
    assert (workspace_dir / "obfuscated.sql").exists()
    assert (workspace_dir / "mapping.json").exists()
    assert (workspace_dir / "context.json").exists()
    assert (workspace_dir / "llm_instructions.md").exists()
    assert (workspace_dir / "mapping.schema.json").exists()
    assert (workspace_dir / "context.schema.json").exists()
    assert (workspace_dir / "integrity.schema.json").exists()
    assert (workspace_dir / "integrity.json").exists()
    instructions = (workspace_dir / "llm_instructions.md").read_text(encoding="utf-8")
    assert "Keep obfuscated identifiers unchanged" in instructions


def test_cli_parse_error_returns_nonzero_with_context(tmp_path: Path, capsys):
    sql_file = tmp_path / "invalid.sql"
    invalid_sql = "SELECT (("  # Unclosed parentheses - will fail to parse
    sql_file.write_text(invalid_sql, encoding="utf-8")

    rc = main(["obfuscate", str(sql_file)])
    captured = capsys.readouterr()

    assert rc == 1
    assert "Error:" in captured.err
    assert "Parse error" in captured.err
    assert "batch" in captured.err


def test_cli_parse_error_in_batch_two(tmp_path: Path, capsys):
    sql_file = tmp_path / "multi_batch.sql"
    # First batch is valid, second batch has syntax error
    sql_content = "SELECT 1;\nGO\nSELECT (("
    sql_file.write_text(sql_content, encoding="utf-8")

    rc = main(["obfuscate", str(sql_file)])
    captured = capsys.readouterr()

    assert rc == 1
    assert "Error:" in captured.err
    assert "batch 2" in captured.err


def test_cli_parse_error_does_not_write_output_file(tmp_path: Path, capsys):
    sql_file = tmp_path / "invalid.sql"
    sql_file.write_text("SELECT ((", encoding="utf-8")

    rc = main(["obfuscate", str(sql_file)])
    capsys.readouterr()

    output_file = tmp_path / "invalid_obfuscated.sql"
    assert rc == 1
    assert not output_file.exists()


def test_cli_obfuscate_stdin_writes_workspace_and_stdout(tmp_path: Path, monkeypatch, capsys):
    workspace = tmp_path / "stdin_ws.obf"
    monkeypatch.setattr("sys.stdin", io.StringIO("SELECT UserId FROM Users;"))

    rc = main(["obfuscate", "-", "--workspace", str(workspace)])
    captured = capsys.readouterr()

    assert rc == 0
    assert "SELECT" in captured.out
    assert (workspace / "original.sql").exists()
    assert (workspace / "obfuscated.sql").exists()


def test_cli_obfuscate_stdout_only_skips_sibling_output_file(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT UserId FROM Users;", encoding="utf-8")

    rc = main(["obfuscate", str(sql_file), "--stdout-only"])
    captured = capsys.readouterr()

    assert rc == 0
    assert "SELECT" in captured.out
    assert (tmp_path / "input_obfuscated.sql").exists() is False
    assert (tmp_path / "input.obf" / "obfuscated.sql").exists()


def test_cli_obfuscate_output_dir_writes_output_file_to_directory(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    out_dir = tmp_path / "outputs"
    sql_file.write_text("SELECT UserId FROM Users;", encoding="utf-8")

    rc = main(["obfuscate", str(sql_file), "--output-dir", str(out_dir)])
    capsys.readouterr()

    assert rc == 0
    assert (out_dir / "input_obfuscated.sql").exists()
    assert (tmp_path / "input_obfuscated.sql").exists() is False


def test_cli_obfuscate_output_dir_rejects_stdin_input(tmp_path: Path, monkeypatch, capsys):
    out_dir = tmp_path / "outputs"
    monkeypatch.setattr("sys.stdin", io.StringIO("SELECT 1;"))

    rc = main(["obfuscate", "-", "--output-dir", str(out_dir)])
    captured = capsys.readouterr()

    assert rc == 1
    assert "--output-dir requires file input" in captured.err


def test_cli_obfuscate_stdout_only_conflicts_with_output_dir(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    out_dir = tmp_path / "outputs"
    sql_file.write_text("SELECT 1;", encoding="utf-8")

    rc = main(["obfuscate", str(sql_file), "--stdout-only", "--output-dir", str(out_dir)])
    captured = capsys.readouterr()

    assert rc == 1
    assert "--stdout-only and --output-dir cannot be used together" in captured.err


def test_cli_roundtrip_stdin_works(tmp_path: Path, monkeypatch, capsys):
    workspace = tmp_path / "stdin_roundtrip.obf"
    monkeypatch.setattr("sys.stdin", io.StringIO("SELECT UserId FROM Users;"))

    rc = main(["roundtrip", "-", "--workspace", str(workspace)])
    captured = capsys.readouterr()

    assert rc == 0
    assert "SELECT" in captured.out
    assert (workspace / "deobfuscated.sql").exists()
    assert (workspace / "reports" / "roundtrip_report.json").exists()


def test_cli_roundtrip_stdout_only_skips_sibling_obfuscated_output_file(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT UserId FROM Users;", encoding="utf-8")

    rc = main(["roundtrip", str(sql_file), "--stdout-only"])
    captured = capsys.readouterr()

    assert rc == 0
    assert "SELECT" in captured.out
    assert (tmp_path / "input_obfuscated.sql").exists() is False
    assert (tmp_path / "input.obf" / "deobfuscated.sql").exists()


def test_cli_roundtrip_output_dir_writes_obfuscated_output_file_to_directory(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    out_dir = tmp_path / "outputs"
    sql_file.write_text("SELECT UserId FROM Users;", encoding="utf-8")

    rc = main(["roundtrip", str(sql_file), "--output-dir", str(out_dir)])
    capsys.readouterr()

    assert rc == 0
    assert (out_dir / "input_obfuscated.sql").exists()
    assert (tmp_path / "input_obfuscated.sql").exists() is False


def test_cli_roundtrip_output_dir_rejects_stdin_input(tmp_path: Path, monkeypatch, capsys):
    out_dir = tmp_path / "outputs"
    monkeypatch.setattr("sys.stdin", io.StringIO("SELECT 1;"))

    rc = main(["roundtrip", "-", "--output-dir", str(out_dir)])
    captured = capsys.readouterr()

    assert rc == 1
    assert "--output-dir requires file input" in captured.err


def test_cli_roundtrip_stdout_only_conflicts_with_output_dir(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    out_dir = tmp_path / "outputs"
    sql_file.write_text("SELECT 1;", encoding="utf-8")

    rc = main(["roundtrip", str(sql_file), "--stdout-only", "--output-dir", str(out_dir)])
    captured = capsys.readouterr()

    assert rc == 1
    assert "--stdout-only and --output-dir cannot be used together" in captured.err


def test_cli_pretty_writes_pretty_output_file(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text(
        "SELECT UserId, UserName FROM Users WHERE Status = 1;",
        encoding="utf-8",
    )

    rc = main(["obfuscate", str(sql_file), "--pretty"])
    captured = capsys.readouterr()

    output_file = tmp_path / "input_obfuscated.sql"
    assert rc == 0
    assert output_file.exists()
    output = output_file.read_text(encoding="utf-8")
    assert "\n" in output
    assert "\n" in captured.out


def test_cli_no_pretty_writes_compact_output_file(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text(
        "SELECT UserId, UserName FROM Users WHERE Status = 1;",
        encoding="utf-8",
    )

    rc = main(["obfuscate", str(sql_file), "--no-pretty"])
    capsys.readouterr()

    output_file = tmp_path / "input_obfuscated.sql"
    assert rc == 0
    assert output_file.exists()
    output = output_file.read_text(encoding="utf-8")
    assert "\n" not in output


def test_cli_allows_custom_workspace_path(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT 1;", encoding="utf-8")
    custom_workspace = tmp_path / "my_workspace"

    rc = main(["obfuscate", str(sql_file), "--workspace", str(custom_workspace)])
    capsys.readouterr()

    assert rc == 0
    assert custom_workspace.exists()
    assert (custom_workspace / "original.sql").exists()
    assert (custom_workspace / "obfuscated.sql").exists()
    assert (custom_workspace / "mapping.json").exists()
    assert (custom_workspace / "context.json").exists()
    assert (custom_workspace / "llm_instructions.md").exists()
    assert (custom_workspace / "mapping.schema.json").exists()
    assert (custom_workspace / "context.schema.json").exists()
    assert (custom_workspace / "integrity.schema.json").exists()
    assert (custom_workspace / "integrity.json").exists()


def test_cli_obfuscate_subcommand_works(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT 1;", encoding="utf-8")

    rc = main(["obfuscate", str(sql_file)])
    captured = capsys.readouterr()

    assert rc == 0
    assert "SELECT" in captured.out
    assert (tmp_path / "input_obfuscated.sql").exists()
    assert (tmp_path / "input.obf" / "mapping.json").exists()


def test_cli_obfuscate_redaction_requires_mode(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT 'secret' AS x;", encoding="utf-8")

    rc = main(["obfuscate", str(sql_file), "--redact-literals"])
    captured = capsys.readouterr()

    assert rc == 1
    assert "Redaction flags require" in captured.err


def test_cli_obfuscate_redact_literals_and_strip_comments(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT 'secret' AS x --comment\nFROM Users WHERE Score = 99;", encoding="utf-8")

    rc = main(
        [
            "obfuscate",
            str(sql_file),
            "--redaction-mode",
            "irreversible",
            "--redact-literals",
            "--strip-comments",
        ]
    )
    captured = capsys.readouterr()

    assert rc == 0
    assert "<REDACTED_STR>" in captured.out
    assert "0" in captured.out
    assert "comment" not in captured.out

    output = (tmp_path / "input_obfuscated.sql").read_text(encoding="utf-8")
    assert "<REDACTED_STR>" in output
    assert "comment" not in output


def test_cli_obfuscate_reversible_redaction_writes_artifacts(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT 'secret';", encoding="utf-8")

    rc = main(
        [
            "obfuscate",
            str(sql_file),
            "--redaction-mode",
            "reversible",
            "--redact-literals",
        ]
    )
    captured = capsys.readouterr()

    assert rc == 0
    assert "__SQL_OBFUSCATOR_STR_" in captured.out
    workspace = tmp_path / "input.obf"
    assert (workspace / "redaction.json").exists()
    assert (workspace / "redaction.schema.json").exists()


def test_cli_deobfuscate_restores_reversible_redacted_literals(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT UserId FROM Users WHERE Status = 'secret' AND Score = 99;", encoding="utf-8")
    assert (
        main(
            [
                "obfuscate",
                str(sql_file),
                "--redaction-mode",
                "reversible",
                "--redact-literals",
            ]
        )
        == 0
    )
    capsys.readouterr()

    edited_path = tmp_path / "input.obf" / "obfuscated.sql"
    rc = main(
        [
            "deobfuscate",
            "--workspace",
            str(tmp_path / "input.obf"),
            "--input",
            str(edited_path),
        ]
    )
    captured = capsys.readouterr()

    assert rc == 0
    assert "secret" in captured.out
    assert "99" in captured.out


def test_cli_deobfuscate_reversible_placeholder_unresolved_returns_nonzero(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT UserId FROM Users WHERE Status = 'secret';", encoding="utf-8")
    assert (
        main(
            [
                "obfuscate",
                str(sql_file),
                "--redaction-mode",
                "reversible",
                "--redact-literals",
            ]
        )
        == 0
    )
    capsys.readouterr()

    edited_path = tmp_path / "edited.sql"
    obfuscated_sql = (tmp_path / "input.obf" / "obfuscated.sql").read_text(encoding="utf-8")
    edited_path.write_text(
        obfuscated_sql.replace("__SQL_OBFUSCATOR_STR_", "__SQL_OBFUSCATOR_STR_BROKEN_", 1),
        encoding="utf-8",
    )

    rc = main(
        [
            "deobfuscate",
            "--workspace",
            str(tmp_path / "input.obf"),
            "--input",
            str(edited_path),
        ]
    )
    captured = capsys.readouterr()

    assert rc == 1
    assert "unresolved mappings" in captured.err


def test_cli_deobfuscate_subcommand_works(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT [UserId] AS TotalAmount FROM Users u;", encoding="utf-8")
    assert main(["obfuscate", str(sql_file)]) == 0
    capsys.readouterr()

    edited_path = tmp_path / "input.obf" / "obfuscated.sql"

    rc = main(
        [
            "deobfuscate",
            "--workspace",
            str(tmp_path / "input.obf"),
            "--input",
            str(edited_path),
        ]
    )
    captured = capsys.readouterr()

    assert rc == 0
    assert "UserId" in captured.out
    assert (tmp_path / "input.obf" / "deobfuscated.sql").exists()
    assert (tmp_path / "input.obf" / "reports" / "deobfuscation_report.json").exists()
    assert (tmp_path / "input.obf" / "reports" / "coverage_report.txt").exists()


def test_cli_deobfuscate_dry_run_no_file_write(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT UserId FROM Users;", encoding="utf-8")
    assert main(["obfuscate", str(sql_file)]) == 0
    capsys.readouterr()

    edited_path = tmp_path / "input.obf" / "obfuscated.sql"
    rc = main(
        [
            "deobfuscate",
            "--workspace",
            str(tmp_path / "input.obf"),
            "--input",
            str(edited_path),
            "--dry-run",
        ]
    )
    captured = capsys.readouterr()

    assert rc == 0
    assert "dry-run summary" in captured.out
    assert (tmp_path / "input.obf" / "deobfuscated.sql").exists() is False
    assert (tmp_path / "input.obf" / "reports" / "deobfuscation_report.json").exists() is False


def test_cli_deobfuscate_dry_run_unresolved_returns_nonzero(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT UserId FROM Users;", encoding="utf-8")
    assert main(["obfuscate", str(sql_file)]) == 0
    capsys.readouterr()

    edited_path = tmp_path / "edited.sql"
    edited_path.write_text("SELECT unknown_identifier FROM unknown_table;", encoding="utf-8")
    rc = main(
        [
            "deobfuscate",
            "--workspace",
            str(tmp_path / "input.obf"),
            "--input",
            str(edited_path),
            "--dry-run",
        ]
    )
    captured = capsys.readouterr()

    assert rc == 1
    assert "unknown_count" in captured.out


def test_cli_deobfuscate_unresolved_non_dry_run_returns_nonzero(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT UserId FROM Users;", encoding="utf-8")
    assert main(["obfuscate", str(sql_file)]) == 0
    capsys.readouterr()

    edited_path = tmp_path / "edited.sql"
    edited_path.write_text("SELECT unknown_identifier FROM unknown_table;", encoding="utf-8")
    rc = main(
        [
            "deobfuscate",
            "--workspace",
            str(tmp_path / "input.obf"),
            "--input",
            str(edited_path),
        ]
    )
    captured = capsys.readouterr()

    assert rc == 1
    assert "unresolved mappings" in captured.err
    assert (tmp_path / "input.obf" / "deobfuscated.sql").exists() is False
    assert (tmp_path / "input.obf" / "reports" / "deobfuscation_report.json").exists() is False


def test_cli_deobfuscate_allow_unresolved_writes_files(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT UserId FROM Users;", encoding="utf-8")
    assert main(["obfuscate", str(sql_file)]) == 0
    capsys.readouterr()

    edited_path = tmp_path / "edited.sql"
    edited_path.write_text("SELECT unknown_identifier FROM unknown_table;", encoding="utf-8")
    rc = main(
        [
            "deobfuscate",
            "--workspace",
            str(tmp_path / "input.obf"),
            "--input",
            str(edited_path),
            "--allow-unresolved",
        ]
    )
    capsys.readouterr()

    assert rc == 0
    assert (tmp_path / "input.obf" / "deobfuscated.sql").exists()
    assert (tmp_path / "input.obf" / "reports" / "deobfuscation_report.json").exists()


def test_cli_deobfuscate_low_confidence_non_dry_run_returns_nonzero(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT UserId FROM Users;", encoding="utf-8")
    assert main(["obfuscate", str(sql_file)]) == 0
    capsys.readouterr()

    obfuscated_sql = (tmp_path / "input.obf" / "obfuscated.sql").read_text(encoding="utf-8")
    edited_path = tmp_path / "edited_low_conf.sql"
    edited_path.write_text(f"{obfuscated_sql}; {obfuscated_sql}", encoding="utf-8")

    rc = main(
        [
            "deobfuscate",
            "--workspace",
            str(tmp_path / "input.obf"),
            "--input",
            str(edited_path),
        ]
    )
    captured = capsys.readouterr()

    assert rc == 1
    assert "low-confidence mappings" in captured.err
    assert (tmp_path / "input.obf" / "deobfuscated.sql").exists() is False


def test_cli_deobfuscate_allow_low_confidence_writes_files(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT UserId FROM Users;", encoding="utf-8")
    assert main(["obfuscate", str(sql_file)]) == 0
    capsys.readouterr()

    obfuscated_sql = (tmp_path / "input.obf" / "obfuscated.sql").read_text(encoding="utf-8")
    edited_path = tmp_path / "edited_low_conf.sql"
    edited_path.write_text(f"{obfuscated_sql}; {obfuscated_sql}", encoding="utf-8")

    rc = main(
        [
            "deobfuscate",
            "--workspace",
            str(tmp_path / "input.obf"),
            "--input",
            str(edited_path),
            "--allow-low-confidence",
        ]
    )
    capsys.readouterr()

    assert rc == 0
    assert (tmp_path / "input.obf" / "deobfuscated.sql").exists()
    report = json.loads(
        (tmp_path / "input.obf" / "reports" / "deobfuscation_report.json").read_text(encoding="utf-8")
    )
    assert report["low_confidence_count"] > 0


def test_cli_validate_before_write_fails_on_low_confidence_by_default(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT UserId FROM Users;", encoding="utf-8")
    assert main(["obfuscate", str(sql_file)]) == 0
    capsys.readouterr()

    obfuscated_sql = (tmp_path / "input.obf" / "obfuscated.sql").read_text(encoding="utf-8")
    edited_path = tmp_path / "edited_low_conf.sql"
    edited_path.write_text(f"{obfuscated_sql}; {obfuscated_sql}", encoding="utf-8")

    rc = main(
        [
            "validate-before-write",
            "--workspace",
            str(tmp_path / "input.obf"),
            "--input",
            str(edited_path),
        ]
    )
    captured = capsys.readouterr()

    assert rc == 1
    assert "Validation failed: low-confidence mappings found" in captured.err
    assert (tmp_path / "input.obf" / "deobfuscated.sql").exists() is False


def test_cli_validate_before_write_allow_low_confidence_writes_output(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT UserId FROM Users;", encoding="utf-8")
    assert main(["obfuscate", str(sql_file)]) == 0
    capsys.readouterr()

    obfuscated_sql = (tmp_path / "input.obf" / "obfuscated.sql").read_text(encoding="utf-8")
    edited_path = tmp_path / "edited_low_conf.sql"
    edited_path.write_text(f"{obfuscated_sql}; {obfuscated_sql}", encoding="utf-8")

    rc = main(
        [
            "validate-before-write",
            "--workspace",
            str(tmp_path / "input.obf"),
            "--input",
            str(edited_path),
            "--allow-low-confidence",
        ]
    )
    capsys.readouterr()

    assert rc == 0
    assert (tmp_path / "input.obf" / "deobfuscated.sql").exists()


def test_cli_validate_before_write_rejects_dry_run_flag(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT 1;", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "validate-before-write",
                "--workspace",
                str(tmp_path / "input.obf"),
                "--input",
                str(sql_file),
                "--dry-run",
            ]
        )
    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert "unrecognized arguments: --dry-run" in captured.err



def test_cli_apply_llm_edits_writes_output_and_report(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT UserId FROM Users; SELECT OrderId FROM Orders;", encoding="utf-8")
    workspace = tmp_path / "input.obf"
    assert main(["obfuscate", str(sql_file), "--workspace", str(workspace), "--no-pretty"]) == 0
    capsys.readouterr()

    context = json.loads((workspace / "context.json").read_text(encoding="utf-8"))
    first_anchor = context["statement_anchors"][0]
    second_anchor = context["statement_anchors"][1]
    edits_path = workspace / "llm_edits.json"
    edits_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "format": "statement_replacements",
                "edits": [
                    {
                        "statement_id": second_anchor["statement_id"],
                        "sql": f"{second_anchor['obfuscated_sql']} WHERE 1 = 1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    rc = main(["apply-llm-edits", "--workspace", str(workspace), "--edits", str(edits_path)])
    captured = capsys.readouterr()

    assert rc == 0
    assert "apply-llm-edits summary:" in captured.out
    applied_path = workspace / "llm_response_obfuscated.sql"
    assert applied_path.exists()
    applied_sql = applied_path.read_text(encoding="utf-8")
    assert applied_sql.startswith(first_anchor["obfuscated_sql"])
    assert f"{second_anchor['obfuscated_sql']} WHERE 1 = 1" in applied_sql
    assert (workspace / "reports" / "llm_edit_application_report.json").exists()



def test_cli_apply_llm_edits_dry_run_skips_file_write(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT UserId FROM Users;", encoding="utf-8")
    workspace = tmp_path / "input.obf"
    assert main(["obfuscate", str(sql_file), "--workspace", str(workspace), "--no-pretty"]) == 0
    capsys.readouterr()

    context = json.loads((workspace / "context.json").read_text(encoding="utf-8"))
    anchor = context["statement_anchors"][0]
    edits_path = workspace / "llm_edits.json"
    edits_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "format": "statement_replacements",
                "edits": [
                    {
                        "statement_id": anchor["statement_id"],
                        "sql": f"{anchor['obfuscated_sql']} WHERE 1 = 1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    rc = main(
        [
            "apply-llm-edits",
            "--workspace",
            str(workspace),
            "--edits",
            str(edits_path),
            "--dry-run",
        ]
    )
    captured = capsys.readouterr()

    assert rc == 0
    assert "apply-llm-edits summary:" in captured.out
    assert (workspace / "llm_response_obfuscated.sql").exists() is False
    assert (workspace / "reports" / "llm_edit_application_report.json").exists() is False



def test_cli_apply_llm_edits_rejects_unknown_statement_id(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT UserId FROM Users;", encoding="utf-8")
    workspace = tmp_path / "input.obf"
    assert main(["obfuscate", str(sql_file), "--workspace", str(workspace), "--no-pretty"]) == 0
    capsys.readouterr()

    edits_path = workspace / "llm_edits.json"
    edits_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "format": "statement_replacements",
                "edits": [
                    {
                        "statement_id": "stmt_9999",
                        "sql": "SELECT anything",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    rc = main(["apply-llm-edits", "--workspace", str(workspace), "--edits", str(edits_path)])
    captured = capsys.readouterr()

    assert rc == 1
    assert "unknown statement_id" in captured.err


def test_cli_roundtrip_help_describes_diff_report_flag(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["roundtrip", "-h"])
    captured = capsys.readouterr()

    assert exc_info.value.code == 0
    assert "--diff-report" in captured.out
    assert "Write unified diff to reports/roundtrip_diff.txt" in captured.out


@pytest.mark.parametrize(
    ("command", "expected_fragments"),
    [
        ("obfuscate", ["sql_file", "--strict-go", "--stdout-only", "--output-dir"]),
        ("deobfuscate", ["--workspace", "--input", "--dry-run", "--allow-unresolved"]),
        ("validate-before-write", ["--workspace", "--input", "--allow-low-confidence"]),
        ("apply-llm-edits", ["--workspace", "--edits", "--dry-run"]),
        ("roundtrip", ["sql_file", "--diff-report", "--stdout-only", "--output-dir"]),
        ("translate", ["--input", "--source-dialect", "--target-dialect", "--stdout-only", "--output-dir"]),
        ("workspace-info", ["--workspace"]),
    ],
)
def test_cli_help_contract_includes_expected_options(command: str, expected_fragments: list[str], capsys):
    with pytest.raises(SystemExit) as exc_info:
        main([command, "-h"])
    captured = capsys.readouterr()

    assert exc_info.value.code == 0
    for fragment in expected_fragments:
        assert fragment in captured.out


def test_cli_obfuscate_sensitive_redaction_policy_requires_columns(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT email FROM users WHERE email = 'a@b.com';", encoding="utf-8")

    rc = main(
        [
            "obfuscate",
            str(sql_file),
            "--redaction-mode",
            "irreversible",
            "--redact-literals",
            "--redaction-policy",
            "sensitive",
        ]
    )
    captured = capsys.readouterr()

    assert rc == 1
    assert "requires --redaction-sensitive-columns" in captured.err


def test_cli_obfuscate_sensitive_redaction_policy_redacts_configured_columns(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text(
        "SELECT email FROM users WHERE email = 'a@b.com' AND status = 'active';",
        encoding="utf-8",
    )

    rc = main(
        [
            "obfuscate",
            str(sql_file),
            "--redaction-mode",
            "irreversible",
            "--redact-literals",
            "--redaction-policy",
            "sensitive",
            "--redaction-sensitive-columns",
            "email",
        ]
    )
    captured = capsys.readouterr()

    assert rc == 0
    assert "a@b.com" not in captured.out
    assert "active" in captured.out


def test_cli_roundtrip_subcommand_works(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT [UserId] FROM Users;", encoding="utf-8")

    rc = main(["roundtrip", str(sql_file)])
    captured = capsys.readouterr()

    assert rc == 0
    assert "UserId" in captured.out
    workspace = tmp_path / "input.obf"
    assert (workspace / "deobfuscated.sql").exists()
    assert (workspace / "reports" / "deobfuscation_report.json").exists()
    assert (workspace / "reports" / "roundtrip_report.json").exists()
    assert (workspace / "reports" / "original_pretty.sql").exists()
    assert (workspace / "reports" / "deobfuscated_pretty.sql").exists()
    assert (workspace / "reports" / "roundtrip_normalized_diff.txt").exists()

    roundtrip_report = json.loads(
        (workspace / "reports" / "roundtrip_report.json").read_text(encoding="utf-8")
    )
    assert "normalized_exact_match" in roundtrip_report
    assert "normalized_diff_line_count" in roundtrip_report


def test_cli_roundtrip_diff_report_file(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT UserId FROM Users;", encoding="utf-8")

    rc = main(["roundtrip", str(sql_file), "--diff-report"])
    capsys.readouterr()

    assert rc == 0
    assert (tmp_path / "input.obf" / "reports" / "roundtrip_diff.txt").exists()


def test_cli_obfuscate_strict_go_rejects_unsupported_separator_form(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT 1;\nGO -- comment\nSELECT 2;", encoding="utf-8")

    rc = main(["obfuscate", str(sql_file), "--strict-go"])
    captured = capsys.readouterr()

    assert rc == 1
    assert "Strict GO validation failed" in captured.err


def test_cli_uses_custom_instruction_template(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT 1;", encoding="utf-8")
    template = tmp_path / "my_template.md"
    template.write_text("# Custom\nUse this exact template.\n", encoding="utf-8")

    rc = main(["obfuscate", str(sql_file), "--instruction-template", str(template)])
    capsys.readouterr()

    assert rc == 0
    instructions = (tmp_path / "input.obf" / "llm_instructions.md").read_text(
        encoding="utf-8"
    )
    assert instructions == "# Custom\nUse this exact template.\n"


def test_cli_preserves_empty_custom_instruction_template(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT UserId FROM Users;", encoding="utf-8")
    template = tmp_path / "my_template.md"
    template.write_text("", encoding="utf-8")

    rc = main(["obfuscate", str(sql_file), "--instruction-template", str(template)])
    capsys.readouterr()

    assert rc == 0
    instructions = (tmp_path / "input.obf" / "llm_instructions.md").read_text(
        encoding="utf-8"
    )
    assert instructions == ""


def test_cli_workspace_info_subcommand(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT UserId FROM Users;", encoding="utf-8")
    assert main(["roundtrip", str(sql_file), "--diff-report"]) in (0, 1)
    capsys.readouterr()

    rc = main(["workspace-info", "--workspace", str(tmp_path / "input.obf")])
    captured = capsys.readouterr()

    assert rc == 0
    assert "workspace:" in captured.out
    assert "mapping entries:" in captured.out
    assert "llm_instructions.md: yes" in captured.out
    assert "reports/original_pretty.sql: yes" in captured.out
    assert "reports/deobfuscated_pretty.sql: yes" in captured.out
    assert "reports/roundtrip_normalized_diff.txt: yes" in captured.out
    assert "translated.sql: no" in captured.out
    assert "reports/translation_report.json: no" in captured.out


def test_cli_workspace_info_missing_workspace(tmp_path: Path, capsys):
    rc = main(["workspace-info", "--workspace", str(tmp_path / "missing.obf")])
    captured = capsys.readouterr()

    assert rc == 1
    assert "Workspace not found" in captured.err


def test_cli_workspace_info_detects_integrity_tampering(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT 1;", encoding="utf-8")
    assert main(["obfuscate", str(sql_file)]) == 0
    capsys.readouterr()

    mapping_path = tmp_path / "input.obf" / "mapping.json"
    mapping_path.write_text(mapping_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    rc = main(["workspace-info", "--workspace", str(tmp_path / "input.obf")])
    captured = capsys.readouterr()

    assert rc == 1
    assert "Integrity check failed" in captured.err


def test_cli_deobfuscate_detects_integrity_tampering(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT UserId FROM Users;", encoding="utf-8")
    assert main(["obfuscate", str(sql_file)]) == 0
    capsys.readouterr()

    context_path = tmp_path / "input.obf" / "context.json"
    context_path.write_text(context_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    edited_path = tmp_path / "input.obf" / "obfuscated.sql"

    rc = main(
        [
            "deobfuscate",
            "--workspace",
            str(tmp_path / "input.obf"),
            "--input",
            str(edited_path),
        ]
    )
    captured = capsys.readouterr()

    assert rc == 1
    assert "Integrity check failed" in captured.err


def test_cli_translate_writes_output_file_and_returns_zero(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT [UserId] FROM [Users];", encoding="utf-8")

    rc = main(
        [
            "translate",
            "--input",
            str(sql_file),
            "--source-dialect",
            "tsql",
            "--target-dialect",
            "hive",
        ]
    )
    captured = capsys.readouterr()

    assert rc == 0
    assert "translate summary:" in captured.out
    assert (tmp_path / "input_hive.sql").exists()


def test_cli_translate_report_only_does_not_write_sql_output(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT [UserId] FROM [Users];", encoding="utf-8")
    workspace = tmp_path / "translate_ws"

    rc = main(
        [
            "translate",
            "--input",
            str(sql_file),
            "--source-dialect",
            "tsql",
            "--target-dialect",
            "hive",
            "--report-only",
            "--workspace",
            str(workspace),
        ]
    )
    capsys.readouterr()

    assert rc == 0
    assert (tmp_path / "input_hive.sql").exists() is False
    assert (workspace / "reports" / "translation_report.json").exists()


def test_cli_translate_invalid_dialect_returns_nonzero(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT 1;", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "translate",
                "--input",
                str(sql_file),
                "--source-dialect",
                "postgres",
                "--target-dialect",
                "hive",
            ]
        )
    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert "invalid choice" in captured.err


def test_cli_translate_parse_error_path_returns_nonzero(tmp_path: Path, capsys):
    sql_file = tmp_path / "bad.sql"
    sql_file.write_text("SELECT ((", encoding="utf-8")

    rc = main(
        [
            "translate",
            "--input",
            str(sql_file),
            "--source-dialect",
            "tsql",
            "--target-dialect",
            "hive",
        ]
    )
    captured = capsys.readouterr()

    assert rc == 1
    assert "failed=1" in captured.out


def test_cli_translate_validate_failure_returns_nonzero(tmp_path: Path, monkeypatch, capsys):
    from sql_obfuscator import translation

    sql_file = tmp_path / "input.sql"
    workspace = tmp_path / "translate_ws"
    sql_file.write_text("SELECT [UserId] FROM [Users];", encoding="utf-8")
    original_parse = translation.parse

    def parse_for_test(sql: str, *, dialect: str):
        if dialect == "hive" and "UserId" in sql:
            raise translation.ParseError("forced validation failure")
        return original_parse(sql, dialect=dialect)

    monkeypatch.setattr(translation, "parse", parse_for_test)

    rc = main(
        [
            "translate",
            "--input",
            str(sql_file),
            "--source-dialect",
            "tsql",
            "--target-dialect",
            "hive",
            "--validate",
            "--workspace",
            str(workspace),
        ]
    )
    captured = capsys.readouterr()

    assert rc == 1
    assert "failed=" in captured.out
    assert (workspace / "translated.sql").exists() is False
    assert (workspace / "reports" / "translation_report.json").exists()


def test_cli_translate_workspace_default_translated_sql(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT [UserId] FROM [Users];", encoding="utf-8")
    workspace = tmp_path / "translate_ws"

    rc = main(
        [
            "translate",
            "--input",
            str(sql_file),
            "--source-dialect",
            "tsql",
            "--target-dialect",
            "hive",
            "--workspace",
            str(workspace),
        ]
    )
    capsys.readouterr()

    assert rc == 0
    assert (workspace / "translated.sql").exists()
    assert (workspace / "reports" / "translation_report.json").exists()


def test_cli_translate_stdin_prints_translated_sql(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("SELECT TOP 1 UserId FROM Users;"))

    rc = main(
        [
            "translate",
            "--input",
            "-",
            "--source-dialect",
            "tsql",
            "--target-dialect",
            "hive",
        ]
    )
    captured = capsys.readouterr()

    assert rc == 0
    assert "translate summary:" in captured.out
    assert "LIMIT 1" in captured.out


def test_cli_translate_stdout_only_skips_default_output_file(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    workspace = tmp_path / "translate_ws"
    sql_file.write_text("SELECT TOP 1 UserId FROM Users;", encoding="utf-8")

    rc = main(
        [
            "translate",
            "--input",
            str(sql_file),
            "--source-dialect",
            "tsql",
            "--target-dialect",
            "hive",
            "--stdout-only",
            "--workspace",
            str(workspace),
        ]
    )
    captured = capsys.readouterr()

    assert rc == 0
    assert "translate summary:" in captured.out
    assert "LIMIT 1" in captured.out
    assert (tmp_path / "input_hive.sql").exists() is False
    assert (workspace / "translated.sql").exists() is False
    assert (workspace / "reports" / "translation_report.json").exists()


def test_cli_translate_output_dir_writes_translated_output_to_directory(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    out_dir = tmp_path / "translated"
    sql_file.write_text("SELECT TOP 1 UserId FROM Users;", encoding="utf-8")

    rc = main(
        [
            "translate",
            "--input",
            str(sql_file),
            "--source-dialect",
            "tsql",
            "--target-dialect",
            "hive",
            "--output-dir",
            str(out_dir),
        ]
    )
    capsys.readouterr()

    assert rc == 0
    assert (out_dir / "input_hive.sql").exists()
    assert (tmp_path / "input_hive.sql").exists() is False


def test_cli_translate_output_dir_rejects_stdin_input(tmp_path: Path, monkeypatch, capsys):
    out_dir = tmp_path / "translated"
    monkeypatch.setattr("sys.stdin", io.StringIO("SELECT TOP 1 UserId FROM Users;"))

    rc = main(
        [
            "translate",
            "--input",
            "-",
            "--source-dialect",
            "tsql",
            "--target-dialect",
            "hive",
            "--output-dir",
            str(out_dir),
        ]
    )
    captured = capsys.readouterr()

    assert rc == 1
    assert "--output-dir requires file input" in captured.err


def test_cli_translate_output_dir_conflicts_with_out(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT 1;", encoding="utf-8")
    out_file = tmp_path / "translated.sql"
    out_dir = tmp_path / "translated"

    rc = main(
        [
            "translate",
            "--input",
            str(sql_file),
            "--source-dialect",
            "tsql",
            "--target-dialect",
            "hive",
            "--out",
            str(out_file),
            "--output-dir",
            str(out_dir),
        ]
    )
    captured = capsys.readouterr()

    assert rc == 1
    assert "--out and --output-dir cannot be used together" in captured.err


def test_cli_translate_stdout_only_conflicts_with_output_dir(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT 1;", encoding="utf-8")
    out_dir = tmp_path / "translated"

    rc = main(
        [
            "translate",
            "--input",
            str(sql_file),
            "--source-dialect",
            "tsql",
            "--target-dialect",
            "hive",
            "--stdout-only",
            "--output-dir",
            str(out_dir),
        ]
    )
    captured = capsys.readouterr()

    assert rc == 1
    assert "--stdout-only and --output-dir cannot be used together" in captured.err


def test_cli_translate_stdout_only_conflicts_with_out(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT 1;", encoding="utf-8")
    out_file = tmp_path / "translated.sql"

    rc = main(
        [
            "translate",
            "--input",
            str(sql_file),
            "--source-dialect",
            "tsql",
            "--target-dialect",
            "hive",
            "--out",
            str(out_file),
            "--stdout-only",
        ]
    )
    captured = capsys.readouterr()

    assert rc == 1
    assert "--out and --stdout-only cannot be used together" in captured.err


def test_cli_translate_stdout_only_conflicts_with_report_only(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT 1;", encoding="utf-8")

    rc = main(
        [
            "translate",
            "--input",
            str(sql_file),
            "--source-dialect",
            "tsql",
            "--target-dialect",
            "hive",
            "--report-only",
            "--stdout-only",
        ]
    )
    captured = capsys.readouterr()

    assert rc == 1
    assert "--report-only and --stdout-only cannot be used together" in captured.err


def test_cli_stdin_seed_determinism_obfuscate(tmp_path: Path, monkeypatch, capsys):
    ws1 = tmp_path / "ws1.obf"
    ws2 = tmp_path / "ws2.obf"
    sql = "SELECT UserId, UserName FROM Users;"

    monkeypatch.setattr("sys.stdin", io.StringIO(sql))
    rc1 = main(["obfuscate", "-", "--workspace", str(ws1), "--seed", "42"])
    capsys.readouterr()

    monkeypatch.setattr("sys.stdin", io.StringIO(sql))
    rc2 = main(["obfuscate", "-", "--workspace", str(ws2), "--seed", "42"])
    capsys.readouterr()

    assert rc1 == 0
    assert rc2 == 0
    assert (ws1 / "obfuscated.sql").read_text(encoding="utf-8") == (ws2 / "obfuscated.sql").read_text(encoding="utf-8")



def test_cli_default_llm_instructions_describe_bounded_and_expert_modes(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT UserId FROM Users;", encoding="utf-8")

    rc = main(["obfuscate", str(sql_file)])
    capsys.readouterr()

    assert rc == 0
    instructions = (tmp_path / "input.obf" / "llm_instructions.md").read_text(encoding="utf-8")
    assert "Recommended mode: bounded edit" in instructions
    assert "Expert mode" in instructions
    assert "## Statement Anchors" in instructions
    assert "`stmt_0001`" in instructions
    assert "statement_replacements" in instructions
    assert "apply-llm-edits" in instructions


def test_cli_obfuscate_warns_when_fallback_preserved_statements_exist(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("WAITFOR DELAY '00:00:01';\nSELECT UserId FROM Users;", encoding="utf-8")
    workspace = tmp_path / "input.obf"

    rc = main(["obfuscate", str(sql_file), "--workspace", str(workspace)])
    captured = capsys.readouterr()

    assert rc == 0
    assert "Warning:" in captured.err
    assert "fallback/raw passthrough" in captured.err
    assert (tmp_path / "input_obfuscated.sql").exists()

    report = json.loads((workspace / "reports" / "llm_workflow_report.json").read_text(encoding="utf-8"))
    assert report["llm_safe_requested"] is False
    assert report["llm_safe_approved"] is False
    assert report["obfuscation_summary"]["statement_count"] == 2
    assert report["obfuscation_summary"]["fully_transformed_statement_count"] == 1
    assert report["obfuscation_summary"]["fallback_preserved_statement_count"] == 1
    assert report["obfuscation_summary"]["redacted_literal_count"] == 0
    assert any("parser compatibility fallback/raw passthrough" in item for item in report["recommendations"])

    privacy_report = json.loads((workspace / "reports" / "privacy_summary.json").read_text(encoding="utf-8"))
    assert privacy_report["llm_safe_blocked"] is True
    assert "fallback_preserved_statements" in privacy_report["blocking_identifier_classes"]


def test_cli_obfuscate_llm_safe_blocks_fallback_preserved_statements(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("WAITFOR DELAY '00:00:01';\nSELECT UserId FROM Users;", encoding="utf-8")
    workspace = tmp_path / "input.obf"

    rc = main(["obfuscate", str(sql_file), "--workspace", str(workspace), "--llm-safe"])
    captured = capsys.readouterr()

    assert rc == 1
    assert "LLM-safe validation failed" in captured.err
    assert (tmp_path / "input_obfuscated.sql").exists() is False
    assert (workspace / "obfuscated.sql").exists()

    report = json.loads((workspace / "reports" / "llm_workflow_report.json").read_text(encoding="utf-8"))
    assert report["llm_safe_requested"] is True
    assert report["llm_safe_approved"] is False
    assert report["obfuscation_summary"]["fallback_preserved_statement_count"] == 1


def test_cli_obfuscate_llm_safe_blocks_visible_local_variables(tmp_path: Path, capsys):
    sql_file = tmp_path / "input_vars.sql"
    sql_file.write_text("SELECT @UserId, UserId FROM Users;", encoding="utf-8")
    workspace = tmp_path / "input_vars.obf"

    rc = main(["obfuscate", str(sql_file), "--workspace", str(workspace), "--llm-safe"])
    captured = capsys.readouterr()

    assert rc == 1
    assert "LLM-safe validation failed" in captured.err
    assert "local variable reference" in captured.err
    assert (tmp_path / "input_vars_obfuscated.sql").exists() is False
    assert (workspace / "reports" / "privacy_summary.json").exists()

    privacy_report = json.loads((workspace / "reports" / "privacy_summary.json").read_text(encoding="utf-8"))
    assert privacy_report["llm_safe_blocked"] is True
    assert "local_variables" in privacy_report["blocking_identifier_classes"]
    assert privacy_report["identifier_surface"]["local_variables"]["occurrence_count"] == 1



def test_cli_deobfuscate_updates_llm_workflow_report(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT UserId FROM Users WHERE Status = 'secret';", encoding="utf-8")
    workspace = tmp_path / "input.obf"

    assert (
        main(
            [
                "obfuscate",
                str(sql_file),
                "--workspace",
                str(workspace),
                "--redaction-mode",
                "reversible",
                "--redact-literals",
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
            str(workspace / "obfuscated.sql"),
        ]
    )
    capsys.readouterr()

    assert rc == 0
    report = json.loads((workspace / "reports" / "llm_workflow_report.json").read_text(encoding="utf-8"))
    assert report["llm_safe_requested"] is False
    assert report["llm_safe_approved"] is True
    assert report["deobfuscation_summary"]["unknown_count"] == 0
    assert report["deobfuscation_summary"]["ambiguous_count"] == 0
    assert report["deobfuscation_summary"]["low_confidence_count"] == 0
    assert report["deobfuscation_summary"]["matched_statement_anchor_count"] == 1
    assert report["deobfuscation_summary"]["unmatched_statement_anchor_count"] == 0
    assert report["deobfuscation_summary"]["redaction_unknown_placeholder_count"] == 0
    assert report["deobfuscation_summary"]["redaction_missing_placeholder_count"] == 0


def test_cli_workspace_info_includes_llm_workflow_report(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT UserId FROM Users;", encoding="utf-8")

    assert main(["obfuscate", str(sql_file)]) == 0
    capsys.readouterr()

    rc = main(["workspace-info", "--workspace", str(tmp_path / "input.obf")])
    captured = capsys.readouterr()

    assert rc == 0
    assert "reports/llm_workflow_report.json: yes" in captured.out
    assert "reports/llm_edit_application_report.json: no" in captured.out
    assert "reports/privacy_summary.json: yes" in captured.out
    assert "privacy llm-safe blocked: False" in captured.out



def test_cli_workspace_info_includes_llm_edit_application_report(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT UserId FROM Users;", encoding="utf-8")
    workspace = tmp_path / "input.obf"
    assert main(["obfuscate", str(sql_file), "--workspace", str(workspace), "--no-pretty"]) == 0
    capsys.readouterr()

    context = json.loads((workspace / "context.json").read_text(encoding="utf-8"))
    anchor = context["statement_anchors"][0]
    edits_path = workspace / "llm_edits.json"
    edits_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "format": "statement_replacements",
                "edits": [
                    {
                        "statement_id": anchor["statement_id"],
                        "sql": f"{anchor['obfuscated_sql']} WHERE 1 = 1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert main(["apply-llm-edits", "--workspace", str(workspace), "--edits", str(edits_path)]) == 0
    capsys.readouterr()

    rc = main(["workspace-info", "--workspace", str(workspace)])
    captured = capsys.readouterr()

    assert rc == 0
    assert "reports/llm_edit_application_report.json: yes" in captured.out
    assert "reports/privacy_summary.json: yes" in captured.out
