from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .diagnostics import WorkflowDiagnostic
from .errors import InputFileError, WorkspaceError
from .local_workspace_store import (
    LocalWorkspaceStore,
    LocalWorkspaceView,
    WorkspaceArtifactContent,
    WorkspaceInspection,
)
from .workflow import (
    DeobfuscationSummary,
    DeobfuscationResult,
    LlmSafetyError,
    ObfuscationOptions,
    PreparedWorkspace,
    RoundtripResult,
    StatementReplacementResult,
    StatementReplacementSummary,
    TranslationOptions,
    TranslationSummary,
    TranslationWorkflowResult,
    analyze_deobfuscation,
    apply_statement_replacements,
    prepare_workspace,
    require_safe_deobfuscation,
    translate_document,
    validate_deobfuscation,
    verify_roundtrip,
)


@dataclass(frozen=True)
class LocalWorkspacePreparationSummary:
    workspace_path: Path
    written_artifact_paths: tuple[Path, ...]
    llm_safe_approved: bool
    blocker_count: int
    warning_count: int
    diagnostic_count: int


@dataclass(frozen=True)
class LocalWorkspacePreparation:
    prepared: PreparedWorkspace
    workspace_path: Path
    written_artifact_paths: tuple[Path, ...]
    diagnostics: tuple[WorkflowDiagnostic, ...]
    summary: LocalWorkspacePreparationSummary


@dataclass(frozen=True)
class LocalStatementReplacementSummary:
    workspace_path: Path
    output_path: Path | None
    written_artifact_paths: tuple[Path, ...]
    persisted: bool
    replacement: StatementReplacementSummary


@dataclass(frozen=True)
class LocalStatementReplacement:
    replacement: StatementReplacementResult
    workspace_path: Path
    output_path: Path | None
    written_artifact_paths: tuple[Path, ...]
    summary: LocalStatementReplacementSummary
    diagnostics: tuple[WorkflowDiagnostic, ...] = ()


@dataclass(frozen=True)
class LocalDeobfuscationSummary:
    workspace_path: Path
    output_path: Path | None
    written_artifact_paths: tuple[Path, ...]
    persisted: bool
    deobfuscation: DeobfuscationSummary
    has_unresolved: bool
    has_low_confidence: bool


@dataclass(frozen=True)
class LocalDeobfuscation:
    deobfuscation: DeobfuscationResult
    workspace_path: Path
    output_path: Path | None
    written_artifact_paths: tuple[Path, ...]
    diagnostics: tuple[WorkflowDiagnostic, ...]
    summary: LocalDeobfuscationSummary


@dataclass(frozen=True)
class LocalRoundtripSummary:
    workspace_path: Path
    written_artifact_paths: tuple[Path, ...]
    completed: bool
    exact_match: bool | None
    normalized_exact_match: bool | None
    deobfuscation: DeobfuscationSummary | None


@dataclass(frozen=True)
class LocalRoundtrip:
    prepared: PreparedWorkspace
    roundtrip: RoundtripResult | None
    workspace_path: Path
    written_artifact_paths: tuple[Path, ...]
    diagnostics: tuple[WorkflowDiagnostic, ...]
    summary: LocalRoundtripSummary


@dataclass(frozen=True)
class LocalTranslationSummary:
    workspace_path: Path | None
    written_artifact_paths: tuple[Path, ...]
    succeeded: bool
    translated_sql_persisted: bool
    translation_report_persisted: bool
    translation: TranslationSummary


@dataclass(frozen=True)
class LocalTranslation:
    translation: TranslationWorkflowResult
    workspace_path: Path | None
    written_artifact_paths: tuple[Path, ...]
    diagnostics: tuple[WorkflowDiagnostic, ...]
    summary: LocalTranslationSummary


class LocalWorkspaceApplication:
    """Run host-neutral workflows with local workspace persistence."""

    def __init__(self, *, store: LocalWorkspaceStore | None = None) -> None:
        self.store = store or LocalWorkspaceStore()

    def default_workspace_path(self, input_path: Path) -> Path:
        return self.store.default_workspace_path(input_path)

    def inspect_workspace(self, workspace_path: Path) -> WorkspaceInspection:
        return self.store.inspect_workspace(workspace_path)

    def open_workspace(self, workspace_path: Path) -> LocalWorkspaceView:
        return self.store.open_workspace(workspace_path)

    def load_workspace_artifact(
        self,
        workspace_path: Path,
        relative_path: str | Path,
    ) -> WorkspaceArtifactContent:
        return self.store.load_workspace_artifact(workspace_path, relative_path)

    def prepare_and_save_workspace(
        self,
        sql: str,
        *,
        input_path: Path,
        workspace_path: Path | None = None,
        options: ObfuscationOptions = ObfuscationOptions(),
        instructions_text: str | None = None,
    ) -> LocalWorkspacePreparation:
        try:
            prepared = prepare_workspace(
                sql,
                input_name=input_path.name,
                options=options,
            )
        except LlmSafetyError as exc:
            prepared = exc.prepared
        resolved_workspace_path = workspace_path or self.default_workspace_path(input_path)
        self.store.save_workspace_snapshot(
            workspace_path=resolved_workspace_path,
            input_path=input_path,
            original_sql=sql,
            snapshot=prepared.snapshot,
            instructions_text=(
                instructions_text if instructions_text is not None else prepared.instructions_text
            ),
        )
        self.store.load_workspace_snapshot(resolved_workspace_path)
        written_paths = self._existing_paths(
            resolved_workspace_path,
            _SNAPSHOT_ARTIFACT_PATHS,
        )
        return LocalWorkspacePreparation(
            prepared=prepared,
            workspace_path=resolved_workspace_path,
            written_artifact_paths=written_paths,
            diagnostics=prepared.diagnostics,
            summary=LocalWorkspacePreparationSummary(
                workspace_path=resolved_workspace_path,
                written_artifact_paths=written_paths,
                llm_safe_approved=prepared.safety.approved,
                blocker_count=len(prepared.safety.blockers),
                warning_count=len(prepared.safety.warnings),
                diagnostic_count=len(prepared.diagnostics),
            ),
        )

    def apply_and_save_statement_replacements(
        self,
        workspace_path: Path,
        edits_payload: dict[str, Any],
        *,
        output_path: Path | None = None,
        persist: bool = True,
    ) -> LocalStatementReplacement:
        snapshot = self.store.load_workspace_snapshot(workspace_path)
        replacement = apply_statement_replacements(snapshot, edits_payload)
        if not persist:
            return LocalStatementReplacement(
                replacement=replacement,
                workspace_path=workspace_path,
                output_path=None,
                written_artifact_paths=(),
                summary=LocalStatementReplacementSummary(
                    workspace_path=workspace_path,
                    output_path=None,
                    written_artifact_paths=(),
                    persisted=False,
                    replacement=replacement.summary,
                ),
            )
        resolved_output_path = output_path or workspace_path / "llm_response_obfuscated.sql"
        if resolved_output_path == workspace_path / "obfuscated.sql":
            raise WorkspaceError("apply-llm-edits cannot overwrite workspace obfuscated.sql")
        self._write_text(resolved_output_path, replacement.applied_obfuscated_sql)
        self.store.save_llm_edit_application_report(
            workspace_path=workspace_path,
            report_payload=replacement.report,
        )
        written_paths = self._existing_explicit_paths(
            resolved_output_path,
            workspace_path / "reports" / "llm_edit_application_report.schema.json",
            workspace_path / "reports" / "llm_edit_application_report.json",
        )
        return LocalStatementReplacement(
            replacement=replacement,
            workspace_path=workspace_path,
            output_path=resolved_output_path,
            written_artifact_paths=written_paths,
            summary=LocalStatementReplacementSummary(
                workspace_path=workspace_path,
                output_path=resolved_output_path,
                written_artifact_paths=written_paths,
                persisted=True,
                replacement=replacement.summary,
            ),
        )

    def analyze_deobfuscation(
        self,
        workspace_path: Path,
        edited_sql: str,
    ) -> LocalDeobfuscation:
        snapshot = self.store.load_workspace_snapshot(workspace_path)
        deobfuscation = analyze_deobfuscation(snapshot, edited_sql)
        return LocalDeobfuscation(
            deobfuscation=deobfuscation,
            workspace_path=workspace_path,
            output_path=None,
            written_artifact_paths=(),
            diagnostics=deobfuscation.diagnostics,
            summary=LocalDeobfuscationSummary(
                workspace_path=workspace_path,
                output_path=None,
                written_artifact_paths=(),
                persisted=False,
                deobfuscation=deobfuscation.summary,
                has_unresolved=deobfuscation.safety.has_unresolved,
                has_low_confidence=deobfuscation.safety.has_low_confidence,
            ),
        )

    def deobfuscate_and_save(
        self,
        workspace_path: Path,
        edited_sql: str,
        *,
        output_path: Path | None = None,
        allow_unresolved: bool = False,
        allow_low_confidence: bool = False,
    ) -> LocalDeobfuscation:
        operation = self.analyze_deobfuscation(workspace_path, edited_sql)
        require_safe_deobfuscation(
            operation.deobfuscation,
            allow_unresolved=allow_unresolved,
            allow_low_confidence=allow_low_confidence,
        )
        return self._save_deobfuscation(
            workspace_path,
            operation.deobfuscation,
            output_path=output_path,
        )

    def validate_and_save_deobfuscation(
        self,
        workspace_path: Path,
        edited_sql: str,
        *,
        output_path: Path | None = None,
        allow_unresolved: bool = False,
        allow_low_confidence: bool = False,
    ) -> LocalDeobfuscation:
        snapshot = self.store.load_workspace_snapshot(workspace_path)
        deobfuscation = validate_deobfuscation(
            snapshot,
            edited_sql,
            allow_unresolved=allow_unresolved,
            allow_low_confidence=allow_low_confidence,
        )
        return self._save_deobfuscation(
            workspace_path,
            deobfuscation,
            output_path=output_path,
        )

    def verify_and_save_roundtrip(
        self,
        sql: str,
        *,
        input_path: Path,
        workspace_path: Path | None = None,
        options: ObfuscationOptions = ObfuscationOptions(),
        instructions_text: str | None = None,
        include_diff_report: bool = False,
    ) -> LocalRoundtrip:
        try:
            roundtrip = verify_roundtrip(
                sql,
                input_name=input_path.name,
                options=options,
            )
            prepared = roundtrip.prepared
        except LlmSafetyError as exc:
            roundtrip = None
            prepared = exc.prepared
        resolved_workspace_path = workspace_path or self.default_workspace_path(input_path)
        self.store.save_workspace_snapshot(
            workspace_path=resolved_workspace_path,
            input_path=input_path,
            original_sql=sql,
            snapshot=prepared.snapshot,
            instructions_text=(
                instructions_text if instructions_text is not None else prepared.instructions_text
            ),
        )
        self.store.load_workspace_snapshot(resolved_workspace_path)
        written_paths = list(self._existing_paths(resolved_workspace_path, _SNAPSHOT_ARTIFACT_PATHS))
        if roundtrip is not None:
            deobfuscation = roundtrip.deobfuscation
            self.store.save_deobfuscation_artifacts(
                workspace_path=resolved_workspace_path,
                deobfuscated_sql=deobfuscation.deobfuscated_sql,
                report_payload=deobfuscation.report,
            )
            self.store.save_llm_workflow_report_if_present(
                workspace_path=resolved_workspace_path,
                report_payload=deobfuscation.llm_workflow_report,
            )
            self.store.save_roundtrip_reports(
                workspace_path=resolved_workspace_path,
                report_payload=roundtrip.report,
                diff_text=roundtrip.artifacts.diff_text if include_diff_report else None,
                original_pretty_sql=roundtrip.artifacts.original_pretty_sql,
                deobfuscated_pretty_sql=roundtrip.artifacts.deobfuscated_pretty_sql,
                normalized_diff_text=roundtrip.artifacts.normalized_diff_text,
            )
            written_paths.extend(
                self._existing_paths(resolved_workspace_path, _ROUNDTRIP_ARTIFACT_PATHS)
            )
            if include_diff_report:
                written_paths.extend(
                    self._existing_explicit_paths(
                        resolved_workspace_path / "reports" / "roundtrip_diff.txt"
                    )
                )
        written_artifact_paths = _deduplicate_paths(written_paths)
        return LocalRoundtrip(
            prepared=prepared,
            roundtrip=roundtrip,
            workspace_path=resolved_workspace_path,
            written_artifact_paths=written_artifact_paths,
            diagnostics=roundtrip.diagnostics if roundtrip is not None else prepared.diagnostics,
            summary=LocalRoundtripSummary(
                workspace_path=resolved_workspace_path,
                written_artifact_paths=written_artifact_paths,
                completed=roundtrip is not None,
                exact_match=roundtrip.exact_match if roundtrip is not None else None,
                normalized_exact_match=(
                    roundtrip.normalized_exact_match if roundtrip is not None else None
                ),
                deobfuscation=(
                    roundtrip.deobfuscation.summary if roundtrip is not None else None
                ),
            ),
        )

    def translate_and_save_artifacts(
        self,
        sql: str,
        *,
        options: TranslationOptions,
        workspace_path: Path | None = None,
        persist_translated_sql: bool = False,
    ) -> LocalTranslation:
        translation = translate_document(sql, options=options)
        written_paths: tuple[Path, ...] = ()
        if workspace_path is not None:
            self.store.save_translation_artifacts(
                workspace_path=workspace_path,
                report_payload=asdict(translation.translation),
                translated_sql=(
                    translation.translation.output_sql
                    if translation.succeeded and persist_translated_sql
                    else None
                ),
            )
            candidates = [
                workspace_path / "reports" / "translation_report.schema.json",
                workspace_path / "reports" / "translation_report.json",
            ]
            if translation.succeeded and persist_translated_sql:
                candidates.append(workspace_path / "translated.sql")
            written_paths = self._existing_explicit_paths(*candidates)
        return LocalTranslation(
            translation=translation,
            workspace_path=workspace_path,
            written_artifact_paths=written_paths,
            diagnostics=translation.diagnostics,
            summary=LocalTranslationSummary(
                workspace_path=workspace_path,
                written_artifact_paths=written_paths,
                succeeded=translation.succeeded,
                translated_sql_persisted=(
                    workspace_path is not None
                    and translation.succeeded
                    and persist_translated_sql
                    and (workspace_path / "translated.sql").exists()
                ),
                translation_report_persisted=(
                    workspace_path is not None
                    and (workspace_path / "reports" / "translation_report.json").exists()
                ),
                translation=translation.summary,
            ),
        )

    def _save_deobfuscation(
        self,
        workspace_path: Path,
        deobfuscation: DeobfuscationResult,
        *,
        output_path: Path | None,
    ) -> LocalDeobfuscation:
        resolved_output_path = output_path or workspace_path / "deobfuscated.sql"
        self._write_text(resolved_output_path, deobfuscation.deobfuscated_sql)
        self.store.save_deobfuscation_artifacts(
            workspace_path=workspace_path,
            deobfuscated_sql=deobfuscation.deobfuscated_sql,
            report_payload=deobfuscation.report,
        )
        self.store.save_llm_workflow_report_if_present(
            workspace_path=workspace_path,
            report_payload=deobfuscation.llm_workflow_report,
        )
        written_paths = self._existing_explicit_paths(
            resolved_output_path,
            workspace_path / "deobfuscated.sql",
            workspace_path / "reports" / "deobfuscation_report.json",
            workspace_path / "reports" / "coverage_report.txt",
            workspace_path / "reports" / "llm_workflow_report.schema.json",
            workspace_path / "reports" / "llm_workflow_report.json",
        )
        return LocalDeobfuscation(
            deobfuscation=deobfuscation,
            workspace_path=workspace_path,
            output_path=resolved_output_path,
            written_artifact_paths=written_paths,
            diagnostics=deobfuscation.diagnostics,
            summary=LocalDeobfuscationSummary(
                workspace_path=workspace_path,
                output_path=resolved_output_path,
                written_artifact_paths=written_paths,
                persisted=True,
                deobfuscation=deobfuscation.summary,
                has_unresolved=deobfuscation.safety.has_unresolved,
                has_low_confidence=deobfuscation.safety.has_low_confidence,
            ),
        )

    def _write_text(self, path: Path, content: str) -> None:
        try:
            path.write_text(content, encoding="utf-8")
        except OSError as exc:
            raise InputFileError(f"Unable to write output file: {path}") from exc

    def _existing_paths(self, workspace_path: Path, relative_paths: tuple[str, ...]) -> tuple[Path, ...]:
        return self._existing_explicit_paths(
            *(workspace_path / relative_path for relative_path in relative_paths)
        )

    def _existing_explicit_paths(self, *paths: Path) -> tuple[Path, ...]:
        return _deduplicate_paths(path for path in paths if path.exists())


_SNAPSHOT_ARTIFACT_PATHS = (
    "original.sql",
    "obfuscated.sql",
    "llm_instructions.md",
    "mapping.schema.json",
    "mapping.json",
    "context.schema.json",
    "context.json",
    "integrity.schema.json",
    "integrity.json",
    "redaction.schema.json",
    "redaction.json",
    "reports/llm_workflow_report.schema.json",
    "reports/llm_workflow_report.json",
    "reports/privacy_summary.schema.json",
    "reports/privacy_summary.json",
)

_ROUNDTRIP_ARTIFACT_PATHS = (
    "deobfuscated.sql",
    "reports/deobfuscation_report.json",
    "reports/coverage_report.txt",
    "reports/llm_workflow_report.schema.json",
    "reports/llm_workflow_report.json",
    "reports/roundtrip_report.json",
    "reports/original_pretty.sql",
    "reports/deobfuscated_pretty.sql",
    "reports/roundtrip_normalized_diff.txt",
)


def _deduplicate_paths(paths: Iterable[Path]) -> tuple[Path, ...]:
    return tuple(dict.fromkeys(paths))
