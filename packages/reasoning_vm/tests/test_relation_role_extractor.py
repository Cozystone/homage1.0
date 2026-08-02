from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from importlib import metadata as importlib_metadata
from typing import Any

import pytest

from packages.cognitive_core.canonical import canonical_digest
from packages.reasoning_vm.deliberator import relation_role_extractor as role_module
from packages.reasoning_vm.deliberator.relation_role_extractor import (
    DependencyBackendFailure,
    DependencyParse,
    DependencyToken,
    MAX_TEXT_CHARS,
    ParserProvenance,
    RelationRoleExtractor,
    SPACY_DISTRIBUTION,
    SPACY_MODEL_DISTRIBUTION,
    SPACY_MODEL_NAME,
    SPACY_MODEL_VERSION,
    SPACY_MODEL_WHEEL_SHA256,
    SPACY_MODEL_WHEEL_URL,
    SPACY_VERSION,
    SpacyRelationRoleExtractor,
    TextSpan,
)


_ACTIVE_TEXT = "Marie Curie discovers radium."
_ACTIVE_SPECIFICATIONS = (
    ("Marie", 1, "compound", "PROPN", "NNP", "Marie", (), 0.99),
    ("Curie", 2, "nsubj", "PROPN", "NNP", "Curie", (), 0.98),
    (
        "discovers",
        None,
        "root",
        "VERB",
        "VBZ",
        "discover",
        ("Tense=Pres", "VerbForm=Fin"),
        0.94,
    ),
    ("radium", 2, "dobj", "NOUN", "NN", "radium", (), 0.91),
    (".", 2, "punct", "PUNCT", ".", ".", (), 0.99),
)
_FAKE_ARTIFACT_SHA256 = canonical_digest(
    {
        "artifact_kind": "deterministic_dependency_fixture",
        "text": _ACTIVE_TEXT,
        "token_specifications": _ACTIVE_SPECIFICATIONS,
    }
)
FAKE_PROVENANCE = ParserProvenance(
    backend_name="deterministic.test.backend",
    backend_version="1.0.0",
    model_name="fixed-dependency-graph",
    model_version="1.0.0",
    model_artifact_sha256=_FAKE_ARTIFACT_SHA256,
)


class DeterministicDependencyBackend:
    """Returns one exact graph; it performs no surface-pattern matching."""

    def __init__(self, parse: DependencyParse) -> None:
        self._parse = parse
        self.calls: list[str] = []

    def parse(self, text: str, /) -> DependencyParse:
        self.calls.append(text)
        if text != self._parse.text:
            raise AssertionError("unexpected deterministic fixture input")
        return self._parse


class ExplodingBackend:
    def parse(self, text: str, /) -> DependencyParse:
        del text
        raise RuntimeError("sensitive parser detail")


class WrongContractBackend:
    def parse(self, text: str, /) -> Any:
        del text
        return object()


def _active_parse() -> DependencyParse:
    text = _ACTIVE_TEXT
    tokens: list[DependencyToken] = []
    cursor = 0
    for index, specification in enumerate(_ACTIVE_SPECIFICATIONS):
        (
            surface,
            head,
            dependency,
            part_of_speech,
            tag,
            lemma,
            morphology,
            confidence,
        ) = specification
        start = text.find(surface, cursor)
        assert start >= cursor
        end = start + len(surface)
        tokens.append(
            DependencyToken(
                index=index,
                text=surface,
                start=start,
                end=end,
                head_index=head,
                dependency=dependency,
                part_of_speech=part_of_speech,
                tag=tag,
                lemma=lemma,
                morphology=tuple(sorted(morphology)),
                confidence=confidence,
            )
        )
        cursor = end
    return DependencyParse(
        text=text,
        tokens=tuple(tokens),
        provenance=FAKE_PROVENANCE,
        confidence=0.96,
    )


def test_deterministic_backend_extracts_roles_spans_and_confidence() -> None:
    parse = _active_parse()
    backend = DeterministicDependencyBackend(parse)
    extractor = RelationRoleExtractor(backend)

    receipt = extractor.extract(parse.text)

    assert backend.calls == [parse.text]
    assert receipt.status == "extracted"
    assert receipt.safe is True
    assert receipt.roles_extracted is True
    assert receipt.provenance == FAKE_PROVENANCE
    assert receipt.direction == "declarative"
    assert receipt.direction_evidence == ()
    assert receipt.polarity == "positive"
    assert receipt.polarity_evidence == ()
    assert receipt.hazards == ()
    assert receipt.subject is not None
    assert receipt.subject.text == "Marie Curie"
    assert receipt.subject.spans == (TextSpan(0, 11),)
    assert receipt.subject.token_indices == (0, 1)
    assert receipt.subject.head_token_index == 1
    assert receipt.subject.lemmas == ("Marie", "Curie")
    assert receipt.subject.parts_of_speech == ("PROPN", "PROPN")
    assert receipt.subject.dependencies == ("compound", "nsubj")
    assert receipt.subject.confidence == 0.96
    assert receipt.relation is not None
    assert receipt.relation.text == "discovers"
    assert receipt.relation.spans == (TextSpan(12, 21),)
    assert receipt.relation.lemmas == ("discover",)
    assert receipt.relation.parts_of_speech == ("VERB",)
    assert receipt.relation.dependencies == ("root",)
    assert receipt.relation.confidence == 0.94
    assert receipt.object is not None
    assert receipt.object.text == "radium"
    assert receipt.object.spans == (TextSpan(22, 28),)
    assert receipt.object.lemmas == ("radium",)
    assert receipt.object.parts_of_speech == ("NOUN",)
    assert receipt.object.dependencies == ("dobj",)
    assert receipt.object.confidence == 0.91
    assert receipt.confidence == 0.91
    serialized = receipt.to_dict()
    receipt_digest = serialized.pop("receipt_digest_sha256")
    assert receipt_digest == receipt.receipt_digest_sha256
    assert receipt_digest == canonical_digest(serialized)
    assert receipt.provenance.model_artifact_sha256 == (
        _FAKE_ARTIFACT_SHA256
    )
    assert not any(
        hasattr(receipt, field)
        for field in ("answer", "fact", "facts", "property_id")
    )


def test_optional_backend_and_invalid_input_fail_closed() -> None:
    extractor = RelationRoleExtractor()

    unavailable = extractor.extract("Athens belongs to Greece.")
    invalid = extractor.extract(" " + "x" * MAX_TEXT_CHARS)

    assert extractor.available is False
    assert unavailable.status == "abstain"
    assert unavailable.reason == "dependency_backend_unavailable"
    assert unavailable.roles_extracted is False
    assert unavailable.provenance is None
    assert invalid.status == "invalid"
    assert invalid.reason == "text_out_of_bounds"


@pytest.mark.parametrize(
    ("backend", "reason"),
    [
        (ExplodingBackend(), "dependency_backend_error"),
        (WrongContractBackend(), "dependency_backend_error"),
    ],
)
def test_backend_failures_do_not_leak_partial_roles(
    backend: Any,
    reason: str,
) -> None:
    receipt = RelationRoleExtractor(backend).extract(
        "Athens belongs to Greece."
    )

    assert receipt.status == "abstain"
    assert receipt.reason == reason
    assert receipt.provenance is None
    assert receipt.subject is None
    assert receipt.relation is None
    assert receipt.object is None
    assert "sensitive" not in receipt.reason


def test_dependency_parse_rejects_cycles_at_backend_boundary() -> None:
    text = "Alpha links beta."
    with pytest.raises(ValueError, match="cycle"):
        DependencyParse(
            text=text,
            tokens=(
                DependencyToken(
                    index=0,
                    text="Alpha",
                    start=0,
                    end=5,
                    head_index=1,
                    dependency="nsubj",
                    part_of_speech="PROPN",
                    tag="NNP",
                    lemma="Alpha",
                ),
                DependencyToken(
                    index=1,
                    text="links",
                    start=6,
                    end=11,
                    head_index=0,
                    dependency="dep",
                    part_of_speech="VERB",
                    tag="VBZ",
                    lemma="link",
                ),
                DependencyToken(
                    index=2,
                    text="beta",
                    start=12,
                    end=16,
                    head_index=None,
                    dependency="root",
                    part_of_speech="NOUN",
                    tag="NN",
                    lemma="beta",
                ),
                DependencyToken(
                    index=3,
                    text=".",
                    start=16,
                    end=17,
                    head_index=2,
                    dependency="punct",
                    part_of_speech="PUNCT",
                    tag=".",
                    lemma=".",
                ),
            ),
            provenance=FAKE_PROVENANCE,
        )


def test_receipt_and_nested_evidence_are_immutable() -> None:
    receipt = RelationRoleExtractor(
        DeterministicDependencyBackend(_active_parse())
    ).extract("Marie Curie discovers radium.")

    with pytest.raises(FrozenInstanceError):
        receipt.status = "abstain"  # type: ignore[misc]
    assert receipt.subject is not None
    with pytest.raises(FrozenInstanceError):
        receipt.subject.text = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        receipt.subject.spans[0].start = 9  # type: ignore[misc]
    with pytest.raises(ValueError, match="digest mismatch"):
        replace(receipt, direction="inverse")


def test_spacy_real_model_extracts_graph_style_and_inverse_questions() -> None:
    """This is intentionally non-skipped: the pinned local model is a gate."""

    extractor = SpacyRelationRoleExtractor()
    assert extractor.loaded is False

    forward = extractor.extract(
        "Which social media hashtag is Project Lantern associated with?"
    )
    inverse = extractor.extract("Which country contains Athens?")
    stranded = extractor.extract("Which country is Athens in?")
    possessive = extractor.extract(
        "What is hydrogen's atomic number?"
    )
    nominal_prep = extractor.extract(
        "What is the chemical formula of water?"
    )
    copular_nominal = extractor.extract("What genre is Dune?")

    assert extractor.loaded is True
    assert forward.status == "extracted"
    assert forward.safe is True
    assert forward.provenance == ParserProvenance(
        backend_name=SPACY_DISTRIBUTION,
        backend_version=SPACY_VERSION,
        model_name=SPACY_MODEL_NAME,
        model_version=SPACY_MODEL_VERSION,
        model_artifact_sha256=SPACY_MODEL_WHEEL_SHA256,
    )
    assert forward.subject is not None
    assert forward.subject.text == "Project Lantern"
    assert forward.subject.spans == (TextSpan(30, 45),)
    assert forward.relation is not None
    assert forward.relation.text == "is associated with"
    assert forward.relation.spans == (
        TextSpan(27, 29),
        TextSpan(46, 61),
    )
    assert forward.relation.lemmas == ("be", "associate", "with")
    assert forward.relation.parts_of_speech == ("AUX", "VERB", "ADP")
    assert forward.relation.dependencies == ("root", "acl", "prep")
    assert forward.object is not None
    assert forward.object.text == "Which social media hashtag"
    assert forward.object.spans == (TextSpan(0, 26),)
    assert forward.direction == "forward"
    assert tuple(cue.kind for cue in forward.direction_evidence) == (
        "query_object",
    )
    # spaCy exposes no calibrated dependency confidence; do not invent one.
    assert forward.confidence is None

    assert inverse.status == "extracted"
    assert inverse.subject is not None
    assert inverse.subject.text == "Which country"
    assert inverse.relation is not None
    assert inverse.relation.text == "contains"
    assert inverse.object is not None
    assert inverse.object.text == "Athens"
    assert inverse.direction == "inverse"
    assert tuple(cue.kind for cue in inverse.direction_evidence) == (
        "query_subject",
    )

    assert stranded.status == "extracted"
    assert stranded.subject is not None
    assert stranded.subject.text == "Athens"
    assert stranded.relation is not None
    assert stranded.relation.text == "is in"
    assert stranded.relation.spans == (
        TextSpan(14, 16),
        TextSpan(24, 26),
    )
    assert stranded.object is not None
    assert stranded.object.text == "Which country"
    assert stranded.direction == "forward"

    assert possessive.status == "extracted"
    assert possessive.subject is not None
    assert possessive.subject.text == "hydrogen"
    assert possessive.relation is not None
    assert possessive.relation.text == "is atomic number"
    assert possessive.relation.spans == (
        TextSpan(5, 7),
        TextSpan(19, 32),
    )
    assert possessive.object is not None
    assert possessive.object.text == "What"
    assert possessive.direction == "forward"

    assert nominal_prep.status == "extracted"
    assert nominal_prep.subject is not None
    assert nominal_prep.subject.text == "water"
    assert nominal_prep.relation is not None
    assert nominal_prep.relation.text == "is chemical formula of"
    assert nominal_prep.relation.spans == (
        TextSpan(5, 7),
        TextSpan(12, 31),
    )
    assert nominal_prep.object is not None
    assert nominal_prep.object.text == "What"
    assert nominal_prep.direction == "forward"

    assert copular_nominal.status == "extracted"
    assert copular_nominal.subject is not None
    assert copular_nominal.subject.text == "Dune"
    assert copular_nominal.relation is not None
    assert copular_nominal.relation.text == "genre is"
    assert copular_nominal.relation.spans == (TextSpan(5, 13),)
    assert copular_nominal.object is not None
    assert copular_nominal.object.text == "What"
    assert copular_nominal.direction == "forward"


def test_spacy_real_model_emits_polarity_and_hazard_evidence() -> None:
    """Hazards retain roles but are never marked safe for relation binding."""

    extractor = SpacyRelationRoleExtractor()
    negative = extractor.extract(
        "Which country does Athens not belong to?"
    )
    past = extractor.extract("Which country did Athens belong to?")
    comparison = extractor.extract(
        "Which largest country does Athens belong to?"
    )
    modality = extractor.extract(
        "Which country might Athens belong to?"
    )

    assert negative.status == "hazard"
    assert negative.safe is False
    assert negative.roles_extracted is True
    assert negative.polarity == "negative"
    assert tuple(cue.text for cue in negative.polarity_evidence) == ("not",)
    assert tuple(hazard.kind for hazard in negative.hazards) == ("negation",)
    assert negative.relation is not None
    assert negative.relation.text == "does not belong to"

    assert past.status == "hazard"
    assert past.polarity == "positive"
    assert tuple(hazard.kind for hazard in past.hazards) == ("temporal",)
    assert past.hazards[0].evidence[0].text == "did"

    assert comparison.status == "hazard"
    assert comparison.subject is not None
    assert comparison.subject.text == "Athens"
    assert comparison.object is not None
    assert comparison.object.text == "Which largest country"
    assert tuple(hazard.kind for hazard in comparison.hazards) == (
        "comparison",
    )
    assert comparison.hazards[0].evidence[0].text == "largest"

    assert modality.status == "hazard"
    assert tuple(hazard.kind for hazard in modality.hazards) == ("modality",)
    assert modality.hazards[0].evidence[0].text == "might"


def test_spacy_runtime_version_mismatch_fails_before_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported: list[str] = []

    def version_reader(distribution: str) -> str:
        if distribution == SPACY_DISTRIBUTION:
            return "0.0.0"
        return SPACY_MODEL_VERSION

    def importer(name: str) -> Any:
        imported.append(name)
        raise AssertionError("version gate must run before import")

    monkeypatch.setattr(role_module.importlib_metadata, "version", version_reader)
    monkeypatch.setattr(role_module, "import_module", importer)
    extractor = SpacyRelationRoleExtractor()

    receipt = extractor.extract("Athens belongs to Greece.")

    assert receipt.status == "abstain"
    assert receipt.reason == "dependency_backend_version_mismatch"
    assert receipt.provenance is None
    assert extractor.loaded is False
    assert imported == []


@pytest.mark.parametrize(
    ("installed_model_version", "reason"),
    [
        (None, "dependency_model_unavailable"),
        ("0.0.0", "dependency_model_version_mismatch"),
    ],
)
def test_spacy_model_absence_or_version_mismatch_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    installed_model_version: str | None,
    reason: str,
) -> None:
    def version_reader(distribution: str) -> str:
        if distribution == SPACY_DISTRIBUTION:
            return SPACY_VERSION
        if distribution == SPACY_MODEL_DISTRIBUTION:
            if installed_model_version is None:
                raise importlib_metadata.PackageNotFoundError(distribution)
            return installed_model_version
        raise AssertionError("unexpected distribution")

    monkeypatch.setattr(role_module.importlib_metadata, "version", version_reader)
    extractor = SpacyRelationRoleExtractor()

    receipt = extractor.extract("Athens belongs to Greece.")

    assert receipt.status == "abstain"
    assert receipt.reason == reason
    assert receipt.provenance is None
    assert receipt.roles_extracted is False
    assert extractor.loaded is False


def test_spacy_loader_is_lazy_and_bounded_before_model_access() -> None:
    extractor = SpacyRelationRoleExtractor()

    receipt = extractor.extract("x" * (MAX_TEXT_CHARS + 1))

    assert receipt.status == "invalid"
    assert receipt.reason == "text_out_of_bounds"
    assert extractor.loaded is False


def test_pinned_model_release_provenance_is_exact() -> None:
    assert SPACY_MODEL_WHEEL_URL == (
        "https://github.com/explosion/spacy-models/releases/download/"
        "en_core_web_sm-3.8.0/"
        "en_core_web_sm-3.8.0-py3-none-any.whl"
    )
    assert SPACY_MODEL_WHEEL_SHA256 == (
        "1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85"
    )
