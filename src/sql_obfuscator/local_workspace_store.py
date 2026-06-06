from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import WorkspaceError
from .llm_instructions import build_default_llm_instructions
from .workspace import (
    CONTEXT_JSON_SCHEMA,
    CONTEXT_SCHEMA_VERSION,
    INTEGRITY_JSON_SCHEMA,
    INTEGRITY_SCHEMA_VERSION,
    INTEGRITY_TRACKED_FILES,
    LLM_EDIT_APPLICATION_REPORT_JSON_SCHEMA,
    LLM_WORKFLOW_REPORT_JSON_SCHEMA,
    MAPPING_JSON_SCHEMA,
    PRIVACY_SUMMARY_REPORT_JSON_SCHEMA,
    REDACTION_JSON_SCHEMA,
    TRANSLATION_REPORT_JSON_SCHEMA,
    WorkspaceSnapshot,
    _validate_context_payload,
    _validate_integrity_payload,
    _validate_llm_workflow_report_payload,
    _validate_mapping_payload,
    _validate_privacy_summary_report_payload,
    _validate_redaction_payload,
)


@dataclass(frozen=True)
class WorkspaceArtifactDefinition:
    relative_path: str
    kind: str
    media_type: str
    read_only: bool = True


WORKSPACE_ARTIFACT_CATALOG = (
    WorkspaceArtifactDefinition("original.sql", "original_sql", "text/sql"),
    WorkspaceArtifactDefinition("obfuscated.sql", "obfuscated_sql", "text/sql"),
    WorkspaceArtifactDefinition(
        "llm_response_obfuscated.sql",
        "llm_response_sql",
        "text/sql",
    ),
    WorkspaceArtifactDefinition("deobfuscated.sql", "deobfuscated_sql", "text/sql"),
    WorkspaceArtifactDefinition("translated.sql", "translated_sql", "text/sql"),
    WorkspaceArtifactDefinition("llm_instructions.md", "llm_instructions", "text/markdown"),
    WorkspaceArtifactDefinition("mapping.schema.json", "schema", "application/json"),
    WorkspaceArtifactDefinition("mapping.json", "mapping", "application/json"),
    WorkspaceArtifactDefinition("context.schema.json", "schema", "application/json"),
    WorkspaceArtifactDefinition("context.json", "context", "application/json"),
    WorkspaceArtifactDefinition("integrity.schema.json", "schema", "application/json"),
    WorkspaceArtifactDefinition("integrity.json", "integrity", "application/json"),
    WorkspaceArtifactDefinition("redaction.schema.json", "schema", "application/json"),
    WorkspaceArtifactDefinition("redaction.json", "redaction", "application/json"),
    WorkspaceArtifactDefinition(
        "reports/privacy_summary.schema.json",
        "schema",
        "application/json",
    ),
    WorkspaceArtifactDefinition(
        "reports/privacy_summary.json",
        "privacy_report",
        "application/json",
    ),
    WorkspaceArtifactDefinition(
        "reports/llm_workflow_report.schema.json",
        "schema",
        "application/json",
    ),
    WorkspaceArtifactDefinition(
        "reports/llm_workflow_report.json",
        "llm_workflow_report",
        "application/json",
    ),
    WorkspaceArtifactDefinition(
        "reports/llm_edit_application_report.schema.json",
        "schema",
        "application/json",
    ),
    WorkspaceArtifactDefinition(
        "reports/llm_edit_application_report.json",
        "llm_edit_application_report",
        "application/json",
    ),
    WorkspaceArtifactDefinition(
        "reports/deobfuscation_report.json",
        "deobfuscation_report",
        "application/json",
    ),
    WorkspaceArtifactDefinition(
        "reports/coverage_report.txt",
        "coverage_report",
        "text/plain",
    ),
    WorkspaceArtifactDefinition(
        "reports/roundtrip_report.json",
        "roundtrip_report",
        "application/json",
    ),
    WorkspaceArtifactDefinition("reports/roundtrip_diff.txt", "diff", "text/plain"),
    WorkspaceArtifactDefinition(
        "reports/original_pretty.sql",
        "normalized_sql",
        "text/sql",
    ),
    WorkspaceArtifactDefinition(
        "reports/deobfuscated_pretty.sql",
        "normalized_sql",
        "text/sql",
    ),
    WorkspaceArtifactDefinition(
        "reports/roundtrip_normalized_diff.txt",
        "diff",
        "text/plain",
    ),
    WorkspaceArtifactDefinition(
        "reports/translation_report.schema.json",
        "schema",
        "application/json",
    ),
    WorkspaceArtifactDefinition(
        "reports/translation_report.json",
        "translation_report",
        "application/json",
    ),
)


@dataclass(frozen=True)
class WorkspaceInspection:
    workspace_path: Path
    dialect: str | None
    seed: int | None
    pretty: bool | None
    batch_count: int | None
    statement_count: int | None
    statement_anchor_count: int
    mapping_entry_count: int | None
    mapping_forward_index_size: int
    mapping_reverse_index_size: int
    integrity_algorithm: str | None
    integrity_tracked_file_count: int
    privacy_llm_safe_blocked: bool | None
    privacy_review_recommended: bool | None
    artifacts: dict[str, bool]
    artifact_statuses: tuple[WorkspaceArtifact, ...] = ()


@dataclass(frozen=True)
class WorkspaceArtifact:
    relative_path: str
    kind: str
    media_type: str
    available: bool
    read_only: bool
    integrity_protected: bool


@dataclass(frozen=True)
class LocalWorkspaceView:
    workspace_path: Path
    inspection: WorkspaceInspection
    artifacts: tuple[WorkspaceArtifact, ...]


@dataclass(frozen=True)
class WorkspaceArtifactContent:
    artifact: WorkspaceArtifact
    text: str


class LocalWorkspaceStore:
    """Persist workspace snapshots and reports in a local directory tree."""

    def default_workspace_path(self, input_path: Path) -> Path:
        return input_path.with_name(f"{input_path.stem}.obf")

    def save_workspace_snapshot(
        self,
        *,
        workspace_path: Path,
        input_path: Path,
        original_sql: str,
        snapshot: WorkspaceSnapshot,
        instructions_text: str | None = None,
    ) -> None:
        self.save_workspace_artifacts(
            workspace_path=workspace_path,
            input_path=input_path,
            original_sql=original_sql,
            obfuscated_sql=snapshot.obfuscated_sql,
            mapping_payload=snapshot.mapping_payload,
            context_payload=snapshot.context_payload,
            llm_instructions_text=instructions_text,
            redaction_payload=snapshot.redaction_payload,
            llm_workflow_report_payload=snapshot.llm_workflow_report or None,
            privacy_summary_payload=snapshot.privacy_summary or None,
        )

    def load_workspace_snapshot(self, workspace_path: Path) -> WorkspaceSnapshot:
        self.validate_workspace_integrity(workspace_path)
        redaction_path = workspace_path / "redaction.json"
        privacy_summary_path = workspace_path / "reports" / "privacy_summary.json"
        llm_workflow_report_path = workspace_path / "reports" / "llm_workflow_report.json"
        context_payload = self.load_context_payload(workspace_path / "context.json")
        return WorkspaceSnapshot(
            obfuscated_sql=self._read_text(workspace_path / "obfuscated.sql"),
            mapping_payload=self.load_mapping_payload(workspace_path / "mapping.json"),
            context_payload={
                key: value
                for key, value in context_payload.items()
                if key != "input_file"
            },
            redaction_payload=(
                self.load_redaction_payload(redaction_path)
                if redaction_path.exists()
                else None
            ),
            privacy_summary=(
                self.load_privacy_summary_report(privacy_summary_path)
                if privacy_summary_path.exists()
                else {}
            ),
            llm_workflow_report=(
                self.load_llm_workflow_report(llm_workflow_report_path)
                if llm_workflow_report_path.exists()
                else {}
            ),
        )

    def save_workspace_artifacts(
        self,
        *,
        workspace_path: Path,
        input_path: Path,
        original_sql: str,
        obfuscated_sql: str,
        mapping_payload: dict[str, Any],
        context_payload: dict[str, Any],
        llm_instructions_text: str | None = None,
        redaction_payload: dict[str, Any] | None = None,
        llm_workflow_report_payload: dict[str, Any] | None = None,
        privacy_summary_payload: dict[str, Any] | None = None,
    ) -> None:
        self._make_directory(workspace_path, context="workspace")
        self._write_text(workspace_path / "original.sql", original_sql)
        self._write_text(workspace_path / "obfuscated.sql", obfuscated_sql)
        self._write_text(
            workspace_path / "llm_instructions.md",
            llm_instructions_text
            if llm_instructions_text is not None
            else build_default_llm_instructions(
                input_name=input_path.name,
                dialect=context_payload.get("dialect", "tsql"),
                statement_anchors=context_payload.get("statement_anchors"),
            ),
        )
        self._write_json(workspace_path / "mapping.schema.json", MAPPING_JSON_SCHEMA)
        self._write_json(workspace_path / "context.schema.json", CONTEXT_JSON_SCHEMA)
        self._write_json(workspace_path / "integrity.schema.json", INTEGRITY_JSON_SCHEMA)

        context = dict(context_payload)
        context.update(
            {
                "schema_version": CONTEXT_SCHEMA_VERSION,
                "input_file": str(input_path),
            }
        )
        self._write_json(workspace_path / "mapping.json", mapping_payload)
        self._write_json(workspace_path / "context.json", context)
        tracked_files = list(INTEGRITY_TRACKED_FILES)
        if redaction_payload is not None:
            self._write_json(workspace_path / "redaction.schema.json", REDACTION_JSON_SCHEMA)
            self._write_json(workspace_path / "redaction.json", redaction_payload)
            tracked_files.append("redaction.json")
        else:
            self._remove_if_exists(workspace_path / "redaction.json")
            self._remove_if_exists(workspace_path / "redaction.schema.json")
        if llm_workflow_report_payload is not None:
            self.save_llm_workflow_report(
                workspace_path=workspace_path,
                report_payload=llm_workflow_report_payload,
            )
        else:
            self._remove_if_exists(workspace_path / "reports" / "llm_workflow_report.json")
            self._remove_if_exists(workspace_path / "reports" / "llm_workflow_report.schema.json")
        if privacy_summary_payload is not None:
            self.save_privacy_summary_report(
                workspace_path=workspace_path,
                report_payload=privacy_summary_payload,
            )
        else:
            self._remove_if_exists(workspace_path / "reports" / "privacy_summary.json")
            self._remove_if_exists(workspace_path / "reports" / "privacy_summary.schema.json")
        self._write_json(
            workspace_path / "integrity.json",
            self._build_integrity_payload(workspace_path, tracked_files=tracked_files),
        )

    def load_mapping_payload(self, mapping_path: Path) -> dict[str, Any]:
        payload = self._read_json(mapping_path)
        _validate_mapping_payload(payload, source=mapping_path)
        return payload

    def load_context_payload(self, context_path: Path) -> dict[str, Any]:
        payload = self._read_json(context_path)
        _validate_context_payload(payload, source=context_path)
        return payload

    def load_redaction_payload(self, redaction_path: Path) -> dict[str, Any]:
        payload = self._read_json(redaction_path)
        _validate_redaction_payload(payload, source=redaction_path)
        return payload

    def load_llm_workflow_report(self, report_path: Path) -> dict[str, Any]:
        payload = self._read_json(report_path)
        _validate_llm_workflow_report_payload(payload, source=report_path)
        return payload

    def load_privacy_summary_report(self, report_path: Path) -> dict[str, Any]:
        payload = self._read_json(report_path)
        _validate_privacy_summary_report_payload(payload, source=report_path)
        return payload

    def validate_workspace_integrity(self, workspace_path: Path) -> dict[str, Any]:
        integrity_path = workspace_path / "integrity.json"
        payload = self._read_json(integrity_path)
        _validate_integrity_payload(payload, source=integrity_path)
        if payload.get("algorithm") != "sha256":
            raise WorkspaceError(
                f"Unsupported integrity algorithm in {integrity_path}: {payload.get('algorithm')}"
            )

        files = payload.get("files", {})
        for rel_path, expected_hash in files.items():
            if not isinstance(rel_path, str) or not isinstance(expected_hash, str):
                raise WorkspaceError(f"Invalid integrity entry in {integrity_path}: {rel_path}")
            target = workspace_path / rel_path
            if not target.exists():
                raise WorkspaceError(f"Integrity check failed: missing file {target}")
            actual_hash = self._sha256_file(target)
            if actual_hash != expected_hash:
                raise WorkspaceError(
                    "Integrity check failed: checksum mismatch for "
                    f"{target}. Expected {expected_hash}, got {actual_hash}."
                )
        return payload

    def inspect_workspace(self, workspace_path: Path) -> WorkspaceInspection:
        if not workspace_path.exists() or not workspace_path.is_dir():
            raise WorkspaceError(f"Workspace not found or not a directory: {workspace_path}")

        mapping_payload = self.load_mapping_payload(workspace_path / "mapping.json")
        context_payload = self.load_context_payload(workspace_path / "context.json")
        integrity_payload = self.validate_workspace_integrity(workspace_path)
        return self._build_workspace_inspection(
            workspace_path,
            mapping_payload=mapping_payload,
            context_payload=context_payload,
            integrity_payload=integrity_payload,
        )

    def open_workspace(self, workspace_path: Path) -> LocalWorkspaceView:
        inspection = self.inspect_workspace(workspace_path)
        return LocalWorkspaceView(
            workspace_path=workspace_path,
            inspection=inspection,
            artifacts=inspection.artifact_statuses,
        )

    def load_workspace_artifact(
        self,
        workspace_path: Path,
        relative_path: str | Path,
    ) -> WorkspaceArtifactContent:
        normalized_path = self._normalize_workspace_artifact_path(relative_path)
        workspace = self.open_workspace(workspace_path)
        artifact = next(
            (
                candidate
                for candidate in workspace.artifacts
                if candidate.relative_path == normalized_path
            ),
            None,
        )
        if artifact is None:
            raise WorkspaceError(f"Unknown workspace artifact path: {relative_path}")
        if not artifact.available:
            raise WorkspaceError(f"Workspace artifact is not available: {normalized_path}")
        return WorkspaceArtifactContent(
            artifact=artifact,
            text=self._read_text(
                self._resolve_workspace_artifact_path(workspace_path, normalized_path)
            ),
        )

    def _build_workspace_inspection(
        self,
        workspace_path: Path,
        *,
        mapping_payload: dict[str, Any],
        context_payload: dict[str, Any],
        integrity_payload: dict[str, Any],
    ) -> WorkspaceInspection:
        privacy_summary_path = workspace_path / "reports" / "privacy_summary.json"
        privacy_summary = (
            self.load_privacy_summary_report(privacy_summary_path)
            if privacy_summary_path.exists()
            else None
        )
        artifact_statuses = self._build_workspace_artifacts(
            workspace_path,
            protected_paths=set(integrity_payload.get("files", {})),
        )
        return WorkspaceInspection(
            workspace_path=workspace_path,
            dialect=context_payload.get("dialect"),
            seed=context_payload.get("seed"),
            pretty=context_payload.get("pretty"),
            batch_count=context_payload.get("batch_count"),
            statement_count=context_payload.get("statement_count"),
            statement_anchor_count=len(context_payload.get("statement_anchors", [])),
            mapping_entry_count=context_payload.get("mapping_entry_count"),
            mapping_forward_index_size=len(mapping_payload.get("forward_index", {})),
            mapping_reverse_index_size=len(mapping_payload.get("reverse_index", {})),
            integrity_algorithm=integrity_payload.get("algorithm"),
            integrity_tracked_file_count=len(integrity_payload.get("files", {})),
            privacy_llm_safe_blocked=(
                privacy_summary.get("llm_safe_blocked")
                if isinstance(privacy_summary, dict)
                else None
            ),
            privacy_review_recommended=(
                privacy_summary.get("manual_review_recommended")
                if isinstance(privacy_summary, dict)
                else None
            ),
            artifacts={
                artifact.relative_path: artifact.available
                for artifact in artifact_statuses
            },
            artifact_statuses=artifact_statuses,
        )

    def _build_workspace_artifacts(
        self,
        workspace_path: Path,
        *,
        protected_paths: set[str],
    ) -> tuple[WorkspaceArtifact, ...]:
        return tuple(
            WorkspaceArtifact(
                relative_path=definition.relative_path,
                kind=definition.kind,
                media_type=definition.media_type,
                available=(workspace_path / definition.relative_path).exists(),
                read_only=definition.read_only,
                integrity_protected=definition.relative_path in protected_paths,
            )
            for definition in WORKSPACE_ARTIFACT_CATALOG
        )

    def _normalize_workspace_artifact_path(self, relative_path: str | Path) -> str:
        candidate = Path(relative_path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise WorkspaceError(
                f"Workspace artifact path must stay within the workspace: {relative_path}"
            )
        normalized = candidate.as_posix()
        if normalized in ("", "."):
            raise WorkspaceError(f"Unknown workspace artifact path: {relative_path}")
        return normalized

    def _resolve_workspace_artifact_path(
        self,
        workspace_path: Path,
        relative_path: str,
    ) -> Path:
        try:
            resolved_workspace_path = workspace_path.resolve(strict=True)
            resolved_artifact_path = (workspace_path / relative_path).resolve(strict=True)
        except OSError as exc:
            raise WorkspaceError(
                f"Unable to resolve workspace artifact path: {relative_path}"
            ) from exc
        if not resolved_artifact_path.is_relative_to(resolved_workspace_path):
            raise WorkspaceError(
                f"Workspace artifact path must stay within the workspace: {relative_path}"
            )
        return resolved_artifact_path

    def save_deobfuscation_artifacts(
        self,
        *,
        workspace_path: Path,
        deobfuscated_sql: str,
        report_payload: dict[str, Any],
    ) -> None:
        reports_path = self._reports_path(workspace_path)
        self._write_text(workspace_path / "deobfuscated.sql", deobfuscated_sql)
        self._write_json(reports_path / "deobfuscation_report.json", report_payload)
        self._write_text(
            reports_path / "coverage_report.txt",
            "\n".join(
                [
                    f"mapped_identifiers: {report_payload.get('mapped_identifiers', 0)}",
                    f"unknown_count: {report_payload.get('unknown_count', 0)}",
                    f"ambiguous_count: {report_payload.get('ambiguous_count', 0)}",
                    f"low_confidence_count: {report_payload.get('low_confidence_count', 0)}",
                    f"matched_statement_anchor_count: {report_payload.get('matched_statement_anchor_count', 0)}",
                    f"unmatched_statement_anchor_count: {report_payload.get('unmatched_statement_anchor_count', 0)}",
                    f"batch_count: {report_payload.get('batch_count', 0)}",
                    f"statement_count: {report_payload.get('statement_count', 0)}",
                    f"unknown_by_kind: {report_payload.get('unknown_by_kind', {})}",
                    f"ambiguous_by_kind: {report_payload.get('ambiguous_by_kind', {})}",
                    f"low_confidence_by_kind: {report_payload.get('low_confidence_by_kind', {})}",
                    "recommendations:",
                    *[
                        f"- {line}"
                        for line in report_payload.get("recommendations", [])
                        if isinstance(line, str)
                    ],
                ]
            )
            + "\n",
        )

    def save_roundtrip_reports(
        self,
        *,
        workspace_path: Path,
        report_payload: dict[str, Any],
        diff_text: str | None = None,
        original_pretty_sql: str | None = None,
        deobfuscated_pretty_sql: str | None = None,
        normalized_diff_text: str | None = None,
    ) -> None:
        reports_path = self._reports_path(workspace_path)
        self._write_json(reports_path / "roundtrip_report.json", report_payload)
        if diff_text is not None:
            self._write_text(reports_path / "roundtrip_diff.txt", diff_text)
        if original_pretty_sql is not None:
            self._write_text(reports_path / "original_pretty.sql", original_pretty_sql)
        if deobfuscated_pretty_sql is not None:
            self._write_text(reports_path / "deobfuscated_pretty.sql", deobfuscated_pretty_sql)
        if normalized_diff_text is not None:
            self._write_text(reports_path / "roundtrip_normalized_diff.txt", normalized_diff_text)

    def save_translation_artifacts(
        self,
        *,
        workspace_path: Path,
        report_payload: dict[str, Any],
        translated_sql: str | None = None,
    ) -> None:
        reports_path = self._reports_path(workspace_path)
        self._write_json(reports_path / "translation_report.schema.json", TRANSLATION_REPORT_JSON_SCHEMA)
        self._write_json(reports_path / "translation_report.json", report_payload)
        if translated_sql is not None:
            self._write_text(workspace_path / "translated.sql", translated_sql)
        else:
            self._remove_if_exists(workspace_path / "translated.sql")

    def save_llm_workflow_report(
        self,
        *,
        workspace_path: Path,
        report_payload: dict[str, Any],
    ) -> None:
        reports_path = self._reports_path(workspace_path)
        self._write_json(reports_path / "llm_workflow_report.schema.json", LLM_WORKFLOW_REPORT_JSON_SCHEMA)
        self._write_json(reports_path / "llm_workflow_report.json", report_payload)

    def save_llm_workflow_report_if_present(
        self,
        *,
        workspace_path: Path,
        report_payload: dict[str, Any],
    ) -> None:
        if (workspace_path / "reports" / "llm_workflow_report.json").exists():
            self.save_llm_workflow_report(
                workspace_path=workspace_path,
                report_payload=report_payload,
            )

    def save_llm_edit_application_report(
        self,
        *,
        workspace_path: Path,
        report_payload: dict[str, Any],
    ) -> None:
        reports_path = self._reports_path(workspace_path)
        self._write_json(
            reports_path / "llm_edit_application_report.schema.json",
            LLM_EDIT_APPLICATION_REPORT_JSON_SCHEMA,
        )
        self._write_json(reports_path / "llm_edit_application_report.json", report_payload)

    def save_privacy_summary_report(
        self,
        *,
        workspace_path: Path,
        report_payload: dict[str, Any],
    ) -> None:
        reports_path = self._reports_path(workspace_path)
        self._write_json(reports_path / "privacy_summary.schema.json", PRIVACY_SUMMARY_REPORT_JSON_SCHEMA)
        self._write_json(reports_path / "privacy_summary.json", report_payload)

    def _reports_path(self, workspace_path: Path) -> Path:
        reports_path = workspace_path / "reports"
        self._make_directory(reports_path, context="reports folder")
        return reports_path

    def _make_directory(self, path: Path, *, context: str) -> None:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise WorkspaceError(f"Unable to create {context}: {path}") from exc

    def _write_text(self, path: Path, content: str) -> None:
        try:
            path.write_text(content, encoding="utf-8")
        except OSError as exc:
            raise WorkspaceError(f"Unable to write workspace file: {path}") from exc

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        try:
            path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise WorkspaceError(f"Unable to write workspace file: {path}") from exc

    def _read_text(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise WorkspaceError(f"Unable to read workspace file: {path}") from exc

    def _remove_if_exists(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            path.unlink()
        except OSError as exc:
            raise WorkspaceError(f"Unable to remove stale workspace file: {path}") from exc

    def _sha256_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                while True:
                    chunk = handle.read(65536)
                    if not chunk:
                        break
                    digest.update(chunk)
        except OSError as exc:
            raise WorkspaceError(f"Unable to read workspace file for hashing: {path}") from exc
        return digest.hexdigest()

    def _build_integrity_payload(
        self,
        workspace_path: Path,
        *,
        tracked_files: list[str],
    ) -> dict[str, Any]:
        files: dict[str, str] = {}
        for rel_path in tracked_files:
            target = workspace_path / rel_path
            files[rel_path] = self._sha256_file(target)
        return {
            "schema_version": INTEGRITY_SCHEMA_VERSION,
            "algorithm": "sha256",
            "files": files,
        }

    def _read_json(self, path: Path) -> dict[str, Any]:
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise WorkspaceError(f"Unable to read workspace file: {path}") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise WorkspaceError(f"Invalid JSON in workspace file: {path}") from exc
        if not isinstance(payload, dict):
            raise WorkspaceError(f"JSON root must be an object in: {path}")
        return payload
