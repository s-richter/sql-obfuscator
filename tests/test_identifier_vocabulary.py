from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from sql_obfuscator.names import IdentifierVocabulary
from sql_obfuscator.pipeline import obfuscate_sql_with_metadata
from sql_obfuscator.workflow import ObfuscationOptions, prepare_workspace


def test_identifier_vocabulary_normalizes_words_into_immutable_tuples():
    vocabulary = IdentifierVocabulary.from_words(
        adjectives=[" calm ", "", "bright"],
        replacements=[" falcon "],
    )

    assert vocabulary.adjectives == ("calm", "bright")
    assert vocabulary.replacements == ("falcon",)
    with pytest.raises(FrozenInstanceError):
        vocabulary.adjectives = ("changed",)


def test_identifier_vocabulary_loads_explicit_word_list_paths(tmp_path: Path):
    adjectives_path = tmp_path / "adjectives.txt"
    replacements_path = tmp_path / "replacements.txt"
    adjectives_path.write_text("calm\nbright\n", encoding="utf-8")
    replacements_path.write_text("falcon\notter\n", encoding="utf-8")

    vocabulary = IdentifierVocabulary.load(
        adjectives_path=adjectives_path,
        replacements_path=replacements_path,
    )

    assert vocabulary.adjectives == ("calm", "bright")
    assert vocabulary.replacements == ("falcon", "otter")
    assert vocabulary.pool_size == 4
    assert vocabulary.safe_pool_size() == 4


def test_identifier_vocabulary_reports_validation_diagnostics():
    vocabulary = IdentifierVocabulary.from_words(
        adjectives=["select", "sea-bad", "clear", "CLEAR"],
        replacements=[],
    )

    diagnostics = vocabulary.validation_diagnostics()

    assert vocabulary.is_valid() is False
    assert {diagnostic.code for diagnostic in diagnostics} == {
        "vocabulary.duplicate_word",
        "vocabulary.empty_word_list",
        "vocabulary.invalid_identifier_shape",
        "vocabulary.no_safe_generated_names",
        "vocabulary.reserved_keyword",
    }


def test_identifier_vocabulary_load_reports_empty_explicit_file(tmp_path: Path):
    adjectives_path = tmp_path / "adjectives.txt"
    replacements_path = tmp_path / "replacements.txt"
    adjectives_path.write_text("", encoding="utf-8")
    replacements_path.write_text("falcon\n", encoding="utf-8")

    vocabulary = IdentifierVocabulary.load(
        adjectives_path=adjectives_path,
        replacements_path=replacements_path,
    )

    assert vocabulary.adjectives == ()
    assert vocabulary.is_valid() is False
    assert any(
        diagnostic.code == "vocabulary.empty_word_list"
        for diagnostic in vocabulary.validation_diagnostics()
    )


def test_identifier_vocabulary_preview_is_seeded_and_repeatable():
    vocabulary = IdentifierVocabulary.from_words(
        adjectives=["calm", "bright"],
        replacements=["falcon", "otter"],
    )

    assert vocabulary.sample_names(count=4, seed=42) == vocabulary.sample_names(
        count=4,
        seed=42,
    )


def test_identifier_vocabulary_providers_do_not_share_state():
    first = IdentifierVocabulary.from_words(
        adjectives=["calm"],
        replacements=["falcon"],
    ).create_provider(seed=7)
    second = IdentifierVocabulary.from_words(
        adjectives=["bright"],
        replacements=["otter"],
    ).create_provider(seed=7)

    assert first.next_name() == "calm_falcon"
    assert second.next_name() == "bright_otter"
    assert first.next_name() == "calm_falcon2"
    assert second.next_name() == "bright_otter2"


def test_pipeline_uses_operation_scoped_identifier_vocabularies():
    first = IdentifierVocabulary.from_words(
        adjectives=["calm"],
        replacements=["falcon"],
    )
    second = IdentifierVocabulary.from_words(
        adjectives=["bright"],
        replacements=["otter"],
    )

    first_result = obfuscate_sql_with_metadata(
        "SELECT UserId FROM Users;",
        seed=7,
        identifier_vocabulary=first,
    )
    second_result = obfuscate_sql_with_metadata(
        "SELECT UserId FROM Users;",
        seed=7,
        identifier_vocabulary=second,
    )

    assert {
        entry["obfuscated_unbracketed"]
        for entry in first_result.mapping_payload["entries"]
    } == {"calm_falcon", "calm_falcon2"}
    assert {
        entry["obfuscated_unbracketed"]
        for entry in second_result.mapping_payload["entries"]
    } == {"bright_otter", "bright_otter2"}


def test_prepare_workspace_accepts_identifier_vocabulary_option():
    vocabulary = IdentifierVocabulary.from_words(
        adjectives=["calm"],
        replacements=["falcon"],
    )

    prepared = prepare_workspace(
        "SELECT UserId FROM Users;",
        input_name="input.sql",
        options=ObfuscationOptions(
            seed=7,
            identifier_vocabulary=vocabulary,
        ),
    )

    assert {
        entry["obfuscated_unbracketed"]
        for entry in prepared.snapshot.mapping_payload["entries"]
    } == {"calm_falcon", "calm_falcon2"}
