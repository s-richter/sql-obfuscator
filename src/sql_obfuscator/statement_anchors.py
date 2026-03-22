from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from sqlglot import exp
from sqlglot.expressions import Expression

from .sqlglot_compat import emit_sql

_PLACEHOLDER_RE = re.compile(r"__SQL_OBFUSCATOR_(?:STR|NUM)_\d+__")


@dataclass(frozen=True)
class StatementAnchor:
    statement_id: str
    batch_index: int
    statement_index: int
    global_statement_index: int
    statement_kind: str
    fingerprint: str
    identifier_tokens: tuple[str, ...]
    placeholder_tokens: tuple[str, ...]
    fallback_preserved: bool
    preview: str


@dataclass(frozen=True)
class StatementAnchorMatch:
    current_global_statement_index: int
    statement_kind: str
    statement_id: str | None
    anchor_batch_index: int | None
    anchor_statement_index: int | None
    anchor_global_statement_index: int | None
    match_strategy: str
    match_score: int


def build_statement_anchor(
    statement: Expression,
    *,
    dialect: str,
    batch_index: int,
    statement_index: int,
    global_statement_index: int,
) -> StatementAnchor:
    canonical_sql = _canonical_statement_sql(statement, dialect=dialect)
    return StatementAnchor(
        statement_id=f"stmt_{global_statement_index:04d}",
        batch_index=batch_index,
        statement_index=statement_index,
        global_statement_index=global_statement_index,
        statement_kind=_statement_kind(statement),
        fingerprint=_fingerprint(canonical_sql),
        identifier_tokens=_identifier_tokens(statement),
        placeholder_tokens=_placeholder_tokens(statement, canonical_sql=canonical_sql),
        fallback_preserved=isinstance(statement.meta.get("raw_sql"), str),
        preview=_preview(canonical_sql),
    )


def anchor_to_payload(anchor: StatementAnchor) -> dict[str, Any]:
    return {
        "statement_id": anchor.statement_id,
        "batch_index": anchor.batch_index,
        "statement_index": anchor.statement_index,
        "global_statement_index": anchor.global_statement_index,
        "statement_kind": anchor.statement_kind,
        "fingerprint": anchor.fingerprint,
        "identifier_tokens": list(anchor.identifier_tokens),
        "placeholder_tokens": list(anchor.placeholder_tokens),
        "fallback_preserved": anchor.fallback_preserved,
        "preview": anchor.preview,
    }


def anchor_from_payload(payload: dict[str, Any]) -> StatementAnchor:
    return StatementAnchor(
        statement_id=str(payload["statement_id"]),
        batch_index=int(payload["batch_index"]),
        statement_index=int(payload["statement_index"]),
        global_statement_index=int(payload["global_statement_index"]),
        statement_kind=str(payload["statement_kind"]),
        fingerprint=str(payload["fingerprint"]),
        identifier_tokens=tuple(str(item) for item in payload.get("identifier_tokens", [])),
        placeholder_tokens=tuple(str(item) for item in payload.get("placeholder_tokens", [])),
        fallback_preserved=bool(payload.get("fallback_preserved", False)),
        preview=str(payload.get("preview", "")),
    )


def build_statement_anchor_matches(
    statements: list[Expression],
    *,
    dialect: str,
    statement_anchor_payloads: list[dict[str, Any]] | None,
) -> list[StatementAnchorMatch]:
    anchors = [anchor_from_payload(payload) for payload in statement_anchor_payloads or []]
    if not anchors:
        return [
            StatementAnchorMatch(
                current_global_statement_index=index,
                statement_kind=_statement_kind(statement),
                statement_id=None,
                anchor_batch_index=None,
                anchor_statement_index=None,
                anchor_global_statement_index=None,
                match_strategy="unavailable",
                match_score=0,
            )
            for index, statement in enumerate(statements, start=1)
        ]

    current_anchors = [
        build_statement_anchor(
            statement,
            dialect=dialect,
            batch_index=0,
            statement_index=0,
            global_statement_index=index,
        )
        for index, statement in enumerate(statements, start=1)
    ]

    matches: dict[int, StatementAnchorMatch] = {}
    unused_anchor_ids = {anchor.statement_id for anchor in anchors}

    _match_exact_fingerprints(current_anchors, anchors, matches, unused_anchor_ids)
    _match_exact_identifier_signatures(current_anchors, anchors, matches, unused_anchor_ids)
    _match_scored(current_anchors, anchors, matches, unused_anchor_ids)

    ordered_matches: list[StatementAnchorMatch] = []
    for current in current_anchors:
        ordered_matches.append(
            matches.get(
                current.global_statement_index,
                StatementAnchorMatch(
                    current_global_statement_index=current.global_statement_index,
                    statement_kind=current.statement_kind,
                    statement_id=None,
                    anchor_batch_index=None,
                    anchor_statement_index=None,
                    anchor_global_statement_index=None,
                    match_strategy="unmatched",
                    match_score=0,
                ),
            )
        )
    return ordered_matches


def match_to_payload(match: StatementAnchorMatch, *, batch_index: int, statement_index: int) -> dict[str, Any]:
    return {
        "current_batch_index": batch_index,
        "current_statement_index": statement_index,
        "current_global_statement_index": match.current_global_statement_index,
        "statement_kind": match.statement_kind,
        "statement_id": match.statement_id,
        "anchor_batch_index": match.anchor_batch_index,
        "anchor_statement_index": match.anchor_statement_index,
        "anchor_global_statement_index": match.anchor_global_statement_index,
        "match_strategy": match.match_strategy,
        "match_score": match.match_score,
    }


def _match_exact_fingerprints(
    current_anchors: list[StatementAnchor],
    anchors: list[StatementAnchor],
    matches: dict[int, StatementAnchorMatch],
    unused_anchor_ids: set[str],
) -> None:
    anchor_map: dict[str, list[StatementAnchor]] = {}
    for anchor in anchors:
        if anchor.statement_id in unused_anchor_ids:
            anchor_map.setdefault(anchor.fingerprint, []).append(anchor)

    for current in current_anchors:
        if current.global_statement_index in matches:
            continue
        candidates = anchor_map.get(current.fingerprint, [])
        anchor = _pick_nearest_unique_anchor(candidates, current.global_statement_index, unused_anchor_ids)
        if anchor is None:
            continue
        matches[current.global_statement_index] = _build_match(
            current=current,
            anchor=anchor,
            match_strategy="exact_fingerprint",
            match_score=100,
        )
        unused_anchor_ids.discard(anchor.statement_id)


def _match_exact_identifier_signatures(
    current_anchors: list[StatementAnchor],
    anchors: list[StatementAnchor],
    matches: dict[int, StatementAnchorMatch],
    unused_anchor_ids: set[str],
) -> None:
    signature_map: dict[tuple[str, tuple[str, ...]], list[StatementAnchor]] = {}
    for anchor in anchors:
        if anchor.statement_id not in unused_anchor_ids or not anchor.identifier_tokens:
            continue
        signature_map.setdefault((anchor.statement_kind, anchor.identifier_tokens), []).append(anchor)

    for current in current_anchors:
        if current.global_statement_index in matches or not current.identifier_tokens:
            continue
        candidates = signature_map.get((current.statement_kind, current.identifier_tokens), [])
        anchor = _pick_nearest_unique_anchor(candidates, current.global_statement_index, unused_anchor_ids)
        if anchor is None:
            continue
        matches[current.global_statement_index] = _build_match(
            current=current,
            anchor=anchor,
            match_strategy="identifier_signature",
            match_score=92,
        )
        unused_anchor_ids.discard(anchor.statement_id)


def _match_scored(
    current_anchors: list[StatementAnchor],
    anchors: list[StatementAnchor],
    matches: dict[int, StatementAnchorMatch],
    unused_anchor_ids: set[str],
) -> None:
    for current in current_anchors:
        if current.global_statement_index in matches:
            continue
        scored = [
            (anchor, _score_anchor_match(current=current, anchor=anchor))
            for anchor in anchors
            if anchor.statement_id in unused_anchor_ids
        ]
        scored = [(anchor, score) for anchor, score in scored if score >= 55]
        if not scored:
            continue
        scored.sort(
            key=lambda item: (
                item[1],
                -abs(current.global_statement_index - item[0].global_statement_index),
            ),
            reverse=True,
        )
        top_anchor, top_score = scored[0]
        runner_up_score = scored[1][1] if len(scored) > 1 else -1
        if top_score - runner_up_score < 8:
            continue
        matches[current.global_statement_index] = _build_match(
            current=current,
            anchor=top_anchor,
            match_strategy="scored_similarity",
            match_score=top_score,
        )
        unused_anchor_ids.discard(top_anchor.statement_id)


def _build_match(
    *,
    current: StatementAnchor,
    anchor: StatementAnchor,
    match_strategy: str,
    match_score: int,
) -> StatementAnchorMatch:
    return StatementAnchorMatch(
        current_global_statement_index=current.global_statement_index,
        statement_kind=current.statement_kind,
        statement_id=anchor.statement_id,
        anchor_batch_index=anchor.batch_index,
        anchor_statement_index=anchor.statement_index,
        anchor_global_statement_index=anchor.global_statement_index,
        match_strategy=match_strategy,
        match_score=match_score,
    )


def _pick_nearest_unique_anchor(
    candidates: list[StatementAnchor],
    current_global_statement_index: int,
    unused_anchor_ids: set[str],
) -> StatementAnchor | None:
    available = [anchor for anchor in candidates if anchor.statement_id in unused_anchor_ids]
    if not available:
        return None
    available.sort(key=lambda anchor: abs(anchor.global_statement_index - current_global_statement_index))
    if len(available) == 1:
        return available[0]
    first_gap = abs(available[0].global_statement_index - current_global_statement_index)
    second_gap = abs(available[1].global_statement_index - current_global_statement_index)
    if first_gap == second_gap:
        return None
    return available[0]


def _score_anchor_match(*, current: StatementAnchor, anchor: StatementAnchor) -> int:
    score = 0
    if current.statement_kind == anchor.statement_kind:
        score += 20
    if current.fallback_preserved == anchor.fallback_preserved:
        score += 8
    identifier_similarity = _jaccard_similarity(current.identifier_tokens, anchor.identifier_tokens)
    if identifier_similarity > 0:
        score += int(round(identifier_similarity * 60))
        if current.identifier_tokens == anchor.identifier_tokens:
            score += 10
    placeholder_similarity = _jaccard_similarity(current.placeholder_tokens, anchor.placeholder_tokens)
    if placeholder_similarity > 0:
        score += int(round(placeholder_similarity * 20))
    order_gap = abs(current.global_statement_index - anchor.global_statement_index)
    score += max(0, 12 - (order_gap * 2))
    return score


def _jaccard_similarity(left: tuple[str, ...], right: tuple[str, ...]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set or not right_set:
        return 0.0
    union = left_set | right_set
    if not union:
        return 0.0
    return len(left_set & right_set) / len(union)


def _canonical_statement_sql(statement: Expression, *, dialect: str) -> str:
    sql_text = emit_sql(statement, dialect=dialect, pretty=False, strip_comments=True)
    return " ".join(sql_text.strip().split())


def _identifier_tokens(statement: Expression) -> tuple[str, ...]:
    if isinstance(statement.meta.get("raw_sql"), str):
        return ()
    tokens = {
        identifier.name
        for identifier in statement.find_all(exp.Identifier)
        if isinstance(identifier.name, str) and identifier.name
    }
    return tuple(sorted(tokens))


def _placeholder_tokens(statement: Expression, *, canonical_sql: str) -> tuple[str, ...]:
    if isinstance(statement.meta.get("raw_sql"), str):
        return tuple(sorted(set(_PLACEHOLDER_RE.findall(canonical_sql))))
    placeholders = {
        literal.this
        for literal in statement.find_all(exp.Literal)
        if literal.is_string and isinstance(literal.this, str) and _PLACEHOLDER_RE.fullmatch(literal.this)
    }
    return tuple(sorted(placeholders))


def _statement_kind(statement: Expression) -> str:
    raw_sql = statement.meta.get("raw_sql")
    if isinstance(raw_sql, str):
        first_token = raw_sql.strip().split(maxsplit=1)
        if first_token:
            return first_token[0].lower()
        return "raw"
    return type(statement).__name__.lower()


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _preview(value: str, max_length: int = 96) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."
