# SQL Identifier Obfuscator

Python CLI project for obfuscating SQL identifiers using an AST-based workflow.

## Current Status

Project scaffold is in place. Core obfuscation logic is not implemented yet.

## Usage

```bash
python obfuscator.py path/to/script.sql
```

## Development

```bash
pip install -e .[dev]
pytest
```

## Git Automation Command

Run:

```powershell
./scripts/git_auto_sync.ps1
```

Dry-run mode (no commit/push):

```powershell
./scripts/git_auto_sync.ps1 -DryRun
```
