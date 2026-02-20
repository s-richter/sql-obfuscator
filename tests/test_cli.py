from __future__ import annotations

import json
from pathlib import Path

from sql_obfuscator.cli import main


def test_cli_missing_file_returns_nonzero(capsys):
    rc = main(["does_not_exist.sql"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "Error:" in captured.err


def test_cli_prints_output_for_valid_sql(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT 1;", encoding="utf-8")

    rc = main([str(sql_file)])
    captured = capsys.readouterr()

    assert rc == 0
    assert "SELECT" in captured.out
    assert "1" in captured.out


def test_cli_writes_obfuscated_output_file(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT 1;", encoding="utf-8")

    rc = main([str(sql_file)])
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

    rc = main([str(sql_file)])
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

    rc = main([str(sql_file)])
    captured = capsys.readouterr()

    assert rc == 1
    assert "Error:" in captured.err
    assert "batch 2" in captured.err


def test_cli_parse_error_does_not_write_output_file(tmp_path: Path, capsys):
    sql_file = tmp_path / "invalid.sql"
    sql_file.write_text("SELECT ((", encoding="utf-8")

    rc = main([str(sql_file)])
    capsys.readouterr()

    output_file = tmp_path / "invalid_obfuscated.sql"
    assert rc == 1
    assert not output_file.exists()


def test_cli_pretty_writes_pretty_output_file(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text(
        "SELECT UserId, UserName FROM Users WHERE Status = 1;",
        encoding="utf-8",
    )

    rc = main([str(sql_file), "--pretty"])
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

    rc = main([str(sql_file), "--no-pretty"])
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

    rc = main([str(sql_file), "--workspace", str(custom_workspace)])
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


def test_cli_deobfuscate_subcommand_works(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT [UserId] AS TotalAmount FROM Users u;", encoding="utf-8")
    assert main([str(sql_file)]) == 0
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
    assert main([str(sql_file)]) == 0
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
    assert main([str(sql_file)]) == 0
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


def test_cli_uses_custom_instruction_template(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT 1;", encoding="utf-8")
    template = tmp_path / "my_template.md"
    template.write_text("# Custom\nUse this exact template.\n", encoding="utf-8")

    rc = main([str(sql_file), "--instruction-template", str(template)])
    capsys.readouterr()

    assert rc == 0
    instructions = (tmp_path / "input.obf" / "llm_instructions.md").read_text(
        encoding="utf-8"
    )
    assert instructions == "# Custom\nUse this exact template.\n"


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


def test_cli_workspace_info_missing_workspace(tmp_path: Path, capsys):
    rc = main(["workspace-info", "--workspace", str(tmp_path / "missing.obf")])
    captured = capsys.readouterr()

    assert rc == 1
    assert "Workspace not found" in captured.err


def test_cli_workspace_info_detects_integrity_tampering(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT 1;", encoding="utf-8")
    assert main([str(sql_file)]) == 0
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
    assert main([str(sql_file)]) == 0
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
