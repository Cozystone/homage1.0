"""Unsigned ATANOR A2 Stage 5 development diagnostic.

This evaluator is deliberately outside ``packages/reasoning_vm``.  It builds a
fresh deterministic dataset from the real read-only B1/S1 stores, writes a
candidate-only JSONL containing exactly ``stem`` and ``choices``, and keeps all
gold metadata out of that JSONL.  The worker subprocess still runs inside the
same repository with inherited filesystem access, so this is payload separation,
not an enforced source or gold security boundary.

The legacy schema label contains ``source-separated-self-measurement`` for
artifact compatibility; it must not be interpreted as an isolation attestation.
The evaluator script and generation plan were not bound into the original
receipt, and its no-write checks do not cover the whole repository.  Therefore
the produced receipt is unsealed diagnostic evidence only: not an external or
independent evaluation, E4/E5 evidence, or a capability claim.  Candidate
results do not influence sampling or membership.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import random
import re
import sqlite3
import struct
import subprocess
import sys
from typing import Any
import unicodedata
import zlib

import numpy as np


SCHEMA = "atanor.a2.stage5.source-separated-self-measurement.v1"
FROZEN_COMMIT = "1399eec46dd3786caf95edfc083ae395888c8277"
SALT = "atanor-a2-stage5-20260725-kestrel-7f3d9c21"
POSITIVE_PER_PREDICATE = 4
POOL_PER_PREDICATE = 28
MAX_DRAWS_PER_PREDICATE = 500_000
MAX_ROWS_PER_STAGE = 4096
MAX_FACTS_PER_STAGE = 256
CHOICE_KEYS = ("A", "B", "C", "D")
STEM_SURFACES = (
    "What is {subject}'s {predicate}?",
    "What is the {predicate} of {subject}?",
    "What {predicate} is {subject}?",
)

REPO = Path(__file__).resolve().parents[1]
PLAN_PATH = REPO / "data/eval/atanor_a2_stage5_fresh_holdout_plan_v1.json"
INPUT_PATH = REPO / "data/eval/atanor_a2_stage5_candidate_inputs_v1.jsonl"
EXPECTED_PATH = REPO / "data/eval/atanor_a2_stage5_evaluator_expected_v1.json"
WORKER1_PATH = REPO / "reports/benchmarks/atanor_a2_stage5_worker_run1_v1.json"
WORKER2_PATH = REPO / "reports/benchmarks/atanor_a2_stage5_worker_run2_v1.json"
RECEIPT_PATH = REPO / "reports/benchmarks/atanor_a2_stage5_fresh_holdout_v1.json"
INCIDENT_PATH = (
    REPO / "reports/benchmarks/atanor_a2_stage5_worker_import_incident_v1.json"
)

RESUME_INPUT_SHA256 = (
    "5fcfa06535b64812d107d6d0b4824caf852a808abb25def8b69b234abf9adbc9"
)
RESUME_EXPECTED_SHA256 = (
    "8f933fe6bf2e783597dbcae0f5d0ca810fde7a8e92ecbe788dcd4d0726c90731"
)

B1_ROOT = REPO / "data/graph_scale/staging_b1_wikidata"
S1_ROOT = REPO / "data/graph_scale/staging_s1_wikidata_literals"

CANDIDATE_SURFACE = (
    "packages/cognitive_core/canonical.py",
    "packages/graph_scale/graph_paths.py",
    "packages/graph_scale/sharded_term_dict.py",
    "packages/graph_scale/triple_store.py",
    "packages/reasoning_vm/deliberator/relation_role_extractor.py",
    "packages/reasoning_vm/deliberator/generic_predicate_socket.py",
    "packages/reasoning_vm/deliberator/generic_predicate_goal.py",
    "packages/reasoning_vm/deliberator/generic_predicate_staging.py",
)

_SAFE_SUBJECT = re.compile(r"[A-Za-z0-9][A-Za-z0-9 .,&()/#+:%-]{0,79}\Z")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _git(*args: str, text: bool = True) -> str | bytes:
    return subprocess.check_output(
        ("git", *args),
        cwd=REPO,
        text=text,
    )


def _candidate_digest_and_freeze_check() -> tuple[str, dict[str, str]]:
    resolved = str(_git("rev-parse", FROZEN_COMMIT)).strip()
    if resolved != FROZEN_COMMIT:
        raise RuntimeError("frozen candidate commit does not resolve exactly")
    changed = subprocess.run(
        ("git", "diff", "--quiet", FROZEN_COMMIT, "--", *CANDIDATE_SURFACE),
        cwd=REPO,
        check=False,
    ).returncode
    if changed != 0:
        raise RuntimeError("candidate surface differs from the frozen commit")
    blobs: dict[str, str] = {}
    body = hashlib.sha256()
    for relative in CANDIDATE_SURFACE:
        raw = _git("show", f"{FROZEN_COMMIT}:{relative}", text=False)
        assert isinstance(raw, bytes)
        blob_digest = hashlib.sha256(raw).hexdigest()
        blobs[relative] = blob_digest
        body.update(relative.encode("utf-8"))
        body.update(b"\0")
        body.update(raw)
        body.update(b"\0")
    return body.hexdigest(), blobs


def _inventory(roots: tuple[Path, ...]) -> list[dict[str, Any]]:
    rows = []
    for root in roots:
        for path in sorted(
            (item for item in root.rglob("*") if item.is_file()),
            key=lambda item: item.as_posix(),
        ):
            stat = path.stat()
            rows.append(
                {
                    "path": path.relative_to(REPO).as_posix(),
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                }
            )
    return rows


def _critical_source_digests() -> dict[str, str]:
    names = (
        B1_ROOT / "B1_WIKIDATA_MANIFEST.json",
        B1_ROOT / "meta.json",
        B1_ROOT / "sources.txt",
        S1_ROOT / "S1_WIKIDATA_LITERAL_MANIFEST.json",
        S1_ROOT / "meta.json",
        S1_ROOT / "sources.txt",
        S1_ROOT / "qid_pid.col",
    )
    return {
        path.relative_to(REPO).as_posix(): _file_digest(path)
        for path in names
    }


class ReadOnlyTerms:
    def __init__(self, root: Path, shards: int = 16) -> None:
        self.shards = shards
        self.connections = []
        for index in range(shards):
            path = root / f"terms_{index:02d}.db"
            uri = f"file:{path.as_posix()}?mode=ro"
            connection = sqlite3.connect(uri, uri=True)
            connection.execute("PRAGMA query_only=ON")
            self.connections.append(connection)

    def lookup(self, term: str) -> int | None:
        shard = zlib.crc32(term.encode("utf-8")) % self.shards
        row = self.connections[shard].execute(
            "SELECT rowid FROM t WHERE term = ?",
            (term,),
        ).fetchone()
        return None if row is None else (int(row[0]) - 1) * self.shards + shard

    def term(self, gid: int) -> str:
        shard = gid % self.shards
        rowid = gid // self.shards + 1
        row = self.connections[shard].execute(
            "SELECT term FROM t WHERE rowid = ?",
            (rowid,),
        ).fetchone()
        return "" if row is None else str(row[0])

    def close(self) -> None:
        for connection in self.connections:
            connection.close()


@dataclass(frozen=True)
class RawFact:
    stage_id: str
    stage_role: str
    row_index: int
    subject_id: int
    subject: str
    predicate: str
    object_value: str


class StageSampler:
    def __init__(
        self,
        *,
        stage_id: str,
        stage_role: str,
        root: Path,
        predicates: tuple[str, ...],
    ) -> None:
        self.stage_id = stage_id
        self.stage_role = stage_role
        self.root = root
        self.predicates = predicates
        self.terms = ReadOnlyTerms(root / "term_shards")
        self.s = np.memmap(root / "s.col", dtype="<i4", mode="r")
        self.p = np.memmap(root / "p.col", dtype="<i4", mode="r")
        self.o = np.memmap(root / "o.col", dtype="<i4", mode="r")
        sorted_path = next(root.glob("s.sorted.*.npy"))
        perm_path = next(root.glob("s.perm.*.npy"))
        self.sorted_s = np.load(sorted_path, mmap_mode="r")
        self.perm = np.load(perm_path, mmap_mode="r")
        self.row_count = len(self.s)
        if not (len(self.p) == len(self.o) == self.row_count):
            raise RuntimeError(f"{stage_id} columns are misaligned")

    def close(self) -> None:
        self.terms.close()

    @staticmethod
    def _label_reason(subject: str, object_value: str) -> str | None:
        if not subject or subject != subject.strip():
            return "subject_whitespace_or_empty"
        if not object_value or object_value != object_value.strip():
            return "object_whitespace_or_empty"
        if unicodedata.normalize("NFKC", subject) != subject:
            return "subject_not_nfkc"
        if unicodedata.normalize("NFKC", object_value) != object_value:
            return "object_not_nfkc"
        if not subject.isascii() or not object_value.isascii():
            return "non_ascii_english_surface"
        if _SAFE_SUBJECT.fullmatch(subject) is None:
            return "subject_not_grammar_safe"
        if len(object_value) > 80 or any(
            ord(character) < 32 or ord(character) == 127
            for character in object_value
        ):
            return "object_out_of_bounds"
        return None

    def subject_rows(self, subject_id: int) -> tuple[int, ...] | None:
        left = int(np.searchsorted(self.sorted_s, subject_id, side="left"))
        right = int(np.searchsorted(self.sorted_s, subject_id, side="right"))
        if right - left > MAX_ROWS_PER_STAGE:
            return None
        return tuple(int(value) for value in self.perm[left:right])

    def facts_for(
        self,
        subject_id: int,
        predicate: str | None = None,
    ) -> tuple[RawFact, ...] | None:
        rows = self.subject_rows(subject_id)
        if rows is None:
            return None
        predicate_id = None if predicate is None else self.terms.lookup(predicate)
        result = []
        for row_index in rows:
            if predicate_id is not None and int(self.p[row_index]) != predicate_id:
                continue
            predicate_value = self.terms.term(int(self.p[row_index]))
            result.append(
                RawFact(
                    stage_id=self.stage_id,
                    stage_role=self.stage_role,
                    row_index=row_index,
                    subject_id=subject_id,
                    subject=self.terms.term(int(self.s[row_index])),
                    predicate=predicate_value,
                    object_value=self.terms.term(int(self.o[row_index])),
                )
            )
        if len(result) > MAX_FACTS_PER_STAGE:
            return None
        return tuple(result)

    def sample_predicate(self, predicate: str) -> tuple[list[RawFact], dict[str, Any]]:
        predicate_id = self.terms.lookup(predicate)
        if predicate_id is None:
            raise RuntimeError(f"graph-owned predicate missing: {predicate}")
        seed_bytes = hashlib.sha256(
            f"{SALT}|{self.stage_id}|{predicate}".encode("utf-8")
        ).digest()
        generator = random.Random(int.from_bytes(seed_bytes, "big"))
        sequence_digest = hashlib.sha256()
        seen_rows: set[int] = set()
        seen_facts: set[tuple[str, str]] = set()
        pool: list[RawFact] = []
        counts: dict[str, int] = {
            "draws": 0,
            "duplicate_row_draw": 0,
            "predicate_mismatch": 0,
            "predicate_match": 0,
            "eligible": 0,
        }
        filter_rejections: dict[str, int] = {}
        rejected_matches: list[dict[str, Any]] = []
        while (
            len(pool) < POOL_PER_PREDICATE
            and counts["draws"] < MAX_DRAWS_PER_PREDICATE
        ):
            row_index = generator.randrange(self.row_count)
            counts["draws"] += 1
            sequence_digest.update(struct.pack("<Q", row_index))
            if row_index in seen_rows:
                counts["duplicate_row_draw"] += 1
                continue
            seen_rows.add(row_index)
            if int(self.p[row_index]) != predicate_id:
                counts["predicate_mismatch"] += 1
                continue
            counts["predicate_match"] += 1
            subject_id = int(self.s[row_index])
            subject = self.terms.term(subject_id)
            object_value = self.terms.term(int(self.o[row_index]))
            reason = self._label_reason(subject, object_value)
            if reason is None:
                subject_rows = self.subject_rows(subject_id)
                if subject_rows is None:
                    reason = "subject_row_bound_exceeded"
            if reason is not None:
                filter_rejections[reason] = filter_rejections.get(reason, 0) + 1
                rejected_matches.append({"row_index": row_index, "reason": reason})
                continue
            key = (subject, object_value)
            if key in seen_facts:
                filter_rejections["duplicate_subject_object"] = (
                    filter_rejections.get("duplicate_subject_object", 0) + 1
                )
                rejected_matches.append(
                    {"row_index": row_index, "reason": "duplicate_subject_object"}
                )
                continue
            seen_facts.add(key)
            counts["eligible"] += 1
            pool.append(
                RawFact(
                    stage_id=self.stage_id,
                    stage_role=self.stage_role,
                    row_index=row_index,
                    subject_id=subject_id,
                    subject=subject,
                    predicate=predicate,
                    object_value=object_value,
                )
            )
        if len(pool) < POOL_PER_PREDICATE:
            raise RuntimeError(
                f"bounded sampling exhausted for {self.stage_id}/{predicate}: "
                f"{len(pool)} eligible"
            )
        funnel = {
            "stage_id": self.stage_id,
            "predicate": predicate,
            "max_draws": MAX_DRAWS_PER_PREDICATE,
            "target_pool": POOL_PER_PREDICATE,
            "sampling_sequence_sha256": sequence_digest.hexdigest(),
            "counts": counts,
            "filter_rejections": filter_rejections,
            "rejected_predicate_matches": rejected_matches,
            "eligible_pool": [asdict(fact) for fact in pool],
        }
        return pool, funnel


def _predicate_surface(predicate: str) -> str:
    return predicate.replace("_", " ").replace("-", " ")


def _stem(fact: RawFact, index: int) -> tuple[str, str]:
    surface_name = ("possessive_nominal", "of_nominal", "copular_fronted_wh")[
        index % len(STEM_SURFACES)
    ]
    return (
        STEM_SURFACES[index % len(STEM_SURFACES)].format(
            subject=fact.subject,
            predicate=_predicate_surface(fact.predicate),
        ),
        surface_name,
    )


def _facts_for_subject_across_stages(
    samplers: tuple[StageSampler, ...],
    subject: str,
) -> tuple[RawFact, ...] | None:
    result: list[RawFact] = []
    for sampler in samplers:
        subject_id = sampler.terms.lookup(subject)
        if subject_id is None:
            continue
        facts = sampler.facts_for(subject_id)
        if facts is None:
            return None
        result.extend(facts)
    return tuple(result)


def _distractors(
    fact: RawFact,
    pool: list[RawFact],
    all_subject_facts: tuple[RawFact, ...],
    *,
    count: int,
    offset: int = 0,
) -> list[str]:
    forbidden = {
        row.object_value
        for row in all_subject_facts
        if row.predicate == fact.predicate
    }
    selected: list[str] = []
    ordered = pool[offset:] + pool[:offset]
    for candidate in ordered:
        value = candidate.object_value
        if value in forbidden or value in selected:
            continue
        if value.casefold() in {item.casefold() for item in (*forbidden, *selected)}:
            continue
        selected.append(value)
        if len(selected) == count:
            return selected
    raise RuntimeError(f"not enough same-predicate distractors for {fact.predicate}")


def _choice_rows(values: list[str]) -> list[list[str]]:
    return [[key, value] for key, value in zip(CHOICE_KEYS, values)]


def _make_positive(
    fact: RawFact,
    pool: list[RawFact],
    all_subject_facts: tuple[RawFact, ...],
    index: int,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    stem, surface = _stem(fact, index)
    gold_position = index % len(CHOICE_KEYS)
    distractors = _distractors(
        fact,
        pool,
        all_subject_facts,
        count=3,
        offset=index % len(pool),
    )
    values = list(distractors)
    values.insert(gold_position, fact.object_value)
    candidate = {"stem": stem, "choices": _choice_rows(values)}
    expected = {
        "kind": "positive",
        "surface": surface,
        "expected_subject": fact.subject,
        "expected_predicate": fact.predicate,
        "expected_gold": fact.object_value,
        "expected_choice_key": CHOICE_KEYS[gold_position],
        "source_fact": asdict(fact),
    }
    reordered = {
        "stem": stem,
        "choices": list(reversed(candidate["choices"])),
    }
    alternate = _distractors(
        fact,
        pool,
        all_subject_facts,
        count=3,
        offset=(index + 11) % len(pool),
    )
    alternate_values = list(alternate)
    alternate_values.insert(gold_position, fact.object_value)
    changed = {"stem": stem, "choices": _choice_rows(alternate_values)}
    variants = [
        {
            "candidate": reordered,
            "expected": {
                **expected,
                "kind": "invariance_variant",
                "variant": "choice_order",
            },
        },
        {
            "candidate": changed,
            "expected": {
                **expected,
                "kind": "invariance_variant",
                "variant": "distractor_values",
            },
        },
    ]
    return candidate, expected, variants


def _negative_item(
    *,
    category: str,
    stem: str,
    choices: list[list[str]],
    source: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        {"stem": stem, "choices": choices},
        {
            "kind": "negative",
            "negative_category": category,
            "expected_final_firing": False,
            "construction_source": source,
        },
    )


def _build_dataset() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    b1_manifest = json.loads(
        (B1_ROOT / "B1_WIKIDATA_MANIFEST.json").read_text(encoding="utf-8")
    )
    s1_manifest = json.loads(
        (S1_ROOT / "S1_WIKIDATA_LITERAL_MANIFEST.json").read_text(encoding="utf-8")
    )
    b1_predicates = tuple(sorted(set(b1_manifest["relation_map"].values())))
    s1_predicates = tuple(
        sorted(
            {
                row["predicate"]
                for row in s1_manifest["property_profile"].values()
            }
        )
    )
    samplers = (
        StageSampler(
            stage_id="b1-wikidata",
            stage_role="entity",
            root=B1_ROOT,
            predicates=b1_predicates,
        ),
        StageSampler(
            stage_id="s1-wikidata-literal",
            stage_role="literal",
            root=S1_ROOT,
            predicates=s1_predicates,
        ),
    )
    pools: dict[tuple[str, str], list[RawFact]] = {}
    funnels: list[dict[str, Any]] = []
    cross_stage_rejections: list[dict[str, Any]] = []
    try:
        for sampler in samplers:
            for predicate in sampler.predicates:
                raw_pool, funnel = sampler.sample_predicate(predicate)
                bounded_pool = []
                for fact in raw_pool:
                    facts = _facts_for_subject_across_stages(samplers, fact.subject)
                    if facts is None:
                        cross_stage_rejections.append(
                            {
                                "stage_id": fact.stage_id,
                                "predicate": predicate,
                                "row_index": fact.row_index,
                                "reason": "cross_stage_context_bound_exceeded",
                            }
                        )
                        continue
                    bounded_pool.append(fact)
                if len(bounded_pool) < 12:
                    raise RuntimeError(
                        f"candidate-blind bounded pool too small for "
                        f"{sampler.stage_id}/{predicate}"
                    )
                pools[(sampler.stage_id, predicate)] = bounded_pool
                funnel["cross_stage_bounded_pool"] = [
                    asdict(fact) for fact in bounded_pool
                ]
                funnels.append(funnel)

        candidates: list[dict[str, Any]] = []
        expected_rows: list[dict[str, Any]] = []
        variants: list[dict[str, Any]] = []
        positives: list[tuple[RawFact, list[RawFact], tuple[RawFact, ...]]] = []
        positive_index = 0
        for sampler in samplers:
            for predicate in sampler.predicates:
                pool = pools[(sampler.stage_id, predicate)]
                selected: list[RawFact] = []
                used_subjects: set[str] = set()
                for fact in pool:
                    if fact.subject in used_subjects:
                        continue
                    selected.append(fact)
                    used_subjects.add(fact.subject)
                    if len(selected) == POSITIVE_PER_PREDICATE:
                        break
                if len(selected) != POSITIVE_PER_PREDICATE:
                    raise RuntimeError(f"not enough unique positive subjects: {predicate}")
                for fact in selected:
                    subject_facts = _facts_for_subject_across_stages(
                        samplers,
                        fact.subject,
                    )
                    assert subject_facts is not None
                    candidate, expected, item_variants = _make_positive(
                        fact,
                        pool,
                        subject_facts,
                        positive_index,
                    )
                    candidates.append(candidate)
                    expected_rows.append(expected)
                    variants.extend(item_variants)
                    positives.append((fact, pool, subject_facts))
                    positive_index += 1

        # All adversarial surfaces are predicate-agnostic dependency forms.
        negatives: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for index in range(4):
            fact, _pool, _facts = positives[index]
            base_choices = candidates[index]["choices"]
            negatives.append(
                _negative_item(
                    category="negation",
                    stem=(
                        f"What is not the {_predicate_surface(fact.predicate)} "
                        f"of {fact.subject}?"
                    ),
                    choices=base_choices,
                    source=asdict(fact),
                )
            )
        for index in range(4, 8):
            fact, pool, _facts = positives[index]
            other = next(row for row in pool if row.subject != fact.subject)
            negatives.append(
                _negative_item(
                    category="comparison",
                    stem=(
                        f"Which has a greater {_predicate_surface(fact.predicate)}, "
                        f"{fact.subject} or {other.subject}?"
                    ),
                    choices=candidates[index]["choices"],
                    source={"left": asdict(fact), "right": asdict(other)},
                )
            )
        for index in range(8, 12):
            fact, _pool, _facts = positives[index]
            negatives.append(
                _negative_item(
                    category="inverse",
                    stem=(
                        f"Which subject has {fact.object_value} as its "
                        f"{_predicate_surface(fact.predicate)}?"
                    ),
                    choices=candidates[index]["choices"],
                    source=asdict(fact),
                )
            )
        for index in range(12, 16):
            fact, pool, _facts = positives[index]
            other = next(row for row in pool if row.subject != fact.subject)
            negatives.append(
                _negative_item(
                    category="ambiguous_subject",
                    stem=(
                        f"What is the {_predicate_surface(fact.predicate)} of "
                        f"{fact.subject} and {other.subject}?"
                    ),
                    choices=candidates[index]["choices"],
                    source={"left": asdict(fact), "right": asdict(other)},
                )
            )

        multi_predicate_sources = []
        multiple_proof_sources = []
        for fact, pool, subject_facts in positives:
            predicates = sorted({row.predicate for row in subject_facts})
            if len(predicates) >= 2 and len(multi_predicate_sources) < 4:
                multi_predicate_sources.append((fact, predicates[1], pool))
            same_values = sorted(
                {
                    row.object_value
                    for row in subject_facts
                    if row.predicate == fact.predicate
                }
            )
            if len(same_values) >= 2 and len(multiple_proof_sources) < 4:
                multiple_proof_sources.append(
                    (fact, same_values, pool, subject_facts)
                )
        if len(multi_predicate_sources) < 4 or len(multiple_proof_sources) < 4:
            raise RuntimeError("bounded pools did not supply required hard negatives")
        for fact, second_predicate, pool in multi_predicate_sources:
            subject_facts = _facts_for_subject_across_stages(samplers, fact.subject)
            assert subject_facts is not None
            distractors = _distractors(fact, pool, subject_facts, count=3)
            values = [fact.object_value, *distractors]
            negatives.append(
                _negative_item(
                    category="ambiguous_predicate",
                    stem=(
                        f"What {_predicate_surface(fact.predicate)} or "
                        f"{_predicate_surface(second_predicate)} is {fact.subject}?"
                    ),
                    choices=_choice_rows(values),
                    source={
                        "fact": asdict(fact),
                        "second_predicate": second_predicate,
                    },
                )
            )
        partial_candidates = [
            row for row in positives if len(row[0].predicate.split("_")) >= 2
        ][:3]
        if len(partial_candidates) < 3:
            raise RuntimeError("not enough multi-token predicates for partial negatives")
        for fact, pool, subject_facts in partial_candidates:
            partial = fact.predicate.split("_")[0]
            distractors = _distractors(fact, pool, subject_facts, count=3)
            negatives.append(
                _negative_item(
                    category="strict_partial_function_only_predicate",
                    stem=f"What is the {partial} of {fact.subject}?",
                    choices=_choice_rows([fact.object_value, *distractors]),
                    source={"fact": asdict(fact), "partial": partial},
                )
            )
        for index in range(3):
            fact, pool, subject_facts = positives[20 + index]
            zero_values = _distractors(
                fact,
                pool,
                subject_facts,
                count=4,
                offset=7,
            )
            stem, _surface = _stem(fact, 20 + index)
            negatives.append(
                _negative_item(
                    category="zero_proof",
                    stem=stem,
                    choices=_choice_rows(zero_values),
                    source=asdict(fact),
                )
            )
        for fact, same_values, pool, subject_facts in multiple_proof_sources:
            distractors = _distractors(fact, pool, subject_facts, count=2)
            stem, _surface = _stem(fact, 1)
            negatives.append(
                _negative_item(
                    category="multiple_proof",
                    stem=stem,
                    choices=_choice_rows([same_values[0], same_values[1], *distractors]),
                    source={
                        "fact": asdict(fact),
                        "provable_values": same_values[:2],
                    },
                )
            )
        if len(negatives) != 30:
            raise RuntimeError(f"negative count drifted: {len(negatives)}")
        for candidate, expected in negatives:
            candidates.append(candidate)
            expected_rows.append(expected)

        # Invariance variants are appended after all primary items.  Each has
        # only stem+choices at the candidate boundary.
        for variant in variants:
            expected = variant["expected"]
            expected["baseline_index"] = next(
                index
                for index, row in enumerate(expected_rows)
                if row.get("kind") == "positive"
                and row["expected_subject"] == expected["expected_subject"]
                and row["expected_predicate"] == expected["expected_predicate"]
                and row["expected_gold"] == expected["expected_gold"]
            )
            candidates.append(variant["candidate"])
            expected_rows.append(expected)

        for line_index, expected in enumerate(expected_rows):
            expected["line_index"] = line_index
        metadata = {
            "schema_version": SCHEMA,
            "salt": SALT,
            "candidate_boundary": "stem_and_choices_only",
            "positive_count": sum(
                row["kind"] == "positive" for row in expected_rows
            ),
            "negative_count": sum(
                row["kind"] == "negative" for row in expected_rows
            ),
            "invariance_variant_count": sum(
                row["kind"] == "invariance_variant" for row in expected_rows
            ),
            "predicate_counts": {
                "b1": len(b1_predicates),
                "s1": len(s1_predicates),
                "total": len(b1_predicates) + len(s1_predicates),
            },
            "answer_position_counts": {
                key: sum(
                    row.get("expected_choice_key") == key
                    and row["kind"] == "positive"
                    for row in expected_rows
                )
                for key in CHOICE_KEYS
            },
            "negative_category_counts": {
                category: sum(
                    row.get("negative_category") == category
                    for row in expected_rows
                )
                for category in sorted(
                    {
                        row["negative_category"]
                        for row in expected_rows
                        if row["kind"] == "negative"
                    }
                )
            },
            "raw_sampling_funnel": funnels,
            "cross_stage_rejections": cross_stage_rejections,
            "expected_rows": expected_rows,
        }
        return candidates, metadata
    finally:
        for sampler in samplers:
            sampler.close()


def _open_socket():
    from packages.reasoning_vm.deliberator.generic_predicate_socket import (
        CompositePredicateSocket,
        PredicateStageSpec,
    )

    return CompositePredicateSocket.open(
        (
            PredicateStageSpec(
                stage_id="b1-wikidata",
                role="entity",
                root=B1_ROOT,
                manifest_name="B1_WIKIDATA_MANIFEST.json",
            ),
            PredicateStageSpec(
                stage_id="s1-wikidata-literal",
                role="literal",
                root=S1_ROOT,
                manifest_name="S1_WIKIDATA_LITERAL_MANIFEST.json",
            ),
        ),
        max_facts_per_stage=MAX_FACTS_PER_STAGE,
        max_rows_examined_per_stage=MAX_ROWS_PER_STAGE,
    )


def _worker(input_path: Path, output_path: Path) -> None:
    # There is intentionally no evaluator metadata or gold path in this
    # subprocess.  It receives only candidate JSONL stem+choices.
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from packages.cognitive_core.canonical import canonical_digest
    from packages.reasoning_vm.deliberator.generic_predicate_goal import (
        compile_generic_predicate_goal,
    )
    from packages.reasoning_vm.deliberator.generic_predicate_staging import (
        consume_generic_predicate_compilation,
        verify_generic_predicate_proof_receipt,
    )
    from packages.reasoning_vm.deliberator.relation_role_extractor import (
        SpacyRelationRoleExtractor,
    )

    rows = []
    extractor = SpacyRelationRoleExtractor()
    with _open_socket() as socket:
        bindings = [binding.to_dict() for binding in socket.stage_bindings]
        with input_path.open(encoding="utf-8") as handle:
            for line in handle:
                item = json.loads(line)
                if set(item) != {"stem", "choices"}:
                    raise RuntimeError("candidate boundary contains evaluator metadata")
                stem = item["stem"]
                choices = tuple(tuple(pair) for pair in item["choices"])
                output: dict[str, Any] = {
                    "role_status": None,
                    "role_reason": None,
                    "role_subject": None,
                    "context_status": None,
                    "context_fact_count": 0,
                    "context_max_facts_per_stage": None,
                    "context_max_rows_examined_per_stage": None,
                    "compiled": False,
                    "compile_status": None,
                    "compile_reason": None,
                    "goal_subject": None,
                    "goal_predicate": None,
                    "goal_digest_sha256": None,
                    "fired": False,
                    "decision_reason": None,
                    "proof_verified": False,
                    "grounded": False,
                    "choice_key": None,
                    "proof": None,
                    "mutation_rejected": None,
                    "all_fact_rows_in_bounds": None,
                    "error_kind": None,
                }
                try:
                    role = extractor.extract(stem)
                    output.update(
                        {
                            "role_status": role.status,
                            "role_reason": role.reason,
                            "role_subject": (
                                None if role.subject is None else role.subject.text
                            ),
                        }
                    )
                    if not role.safe or role.subject is None:
                        rows.append(output)
                        continue
                    context = socket.context_for_subject(role.subject.text)
                    output.update(
                        {
                            "context_status": context.status,
                            "context_fact_count": len(context.facts),
                            "context_max_facts_per_stage": (
                                context.max_facts_per_stage
                            ),
                            "context_max_rows_examined_per_stage": (
                                context.max_rows_examined_per_stage
                            ),
                            "all_fact_rows_in_bounds": all(
                                0 <= fact.row_index
                                < next(
                                    binding.row_count
                                    for binding in context.stage_bindings
                                    if binding.stage_id == fact.stage_id
                                )
                                for fact in context.facts
                            ),
                        }
                    )
                    compilation = compile_generic_predicate_goal(
                        stem,
                        choices,
                        role_receipt=role,
                        context=context,
                    )
                    output.update(
                        {
                            "compiled": compilation.compiled,
                            "compile_status": compilation.status,
                            "compile_reason": compilation.reason,
                        }
                    )
                    if not compilation.compiled:
                        rows.append(output)
                        continue
                    assert compilation.goal is not None
                    output.update(
                        {
                            "goal_subject": compilation.goal.subject,
                            "goal_predicate": compilation.goal.predicate.name,
                            "goal_digest_sha256": canonical_digest(
                                compilation.goal.to_dict()
                            ),
                        }
                    )
                    decision = consume_generic_predicate_compilation(
                        stem,
                        compilation,
                        role_receipt=role,
                        context=context,
                        enabled=True,
                    )
                    output.update(
                        {
                            "fired": decision.engine_fired,
                            "decision_reason": decision.reason,
                            "choice_key": decision.choice_key,
                        }
                    )
                    if decision.receipt is not None:
                        receipt = decision.receipt
                        verified = verify_generic_predicate_proof_receipt(
                            receipt,
                            stem,
                            compilation,
                            role_receipt=role,
                            context=context,
                        )
                        output["proof_verified"] = bool(verified)
                        output["grounded"] = bool(verified)
                        output["proof"] = {
                            "predicate_name": receipt.predicate_name,
                            "predicate_namespace": receipt.predicate_namespace,
                            "predicate_canonical_id": receipt.predicate_canonical_id,
                            "predicate_wikidata_property_id": (
                                receipt.predicate_wikidata_property_id
                            ),
                            "stage_id": receipt.stage_id,
                            "stage_role": receipt.stage_role,
                            "selected_fact_count": receipt.selected_fact_count,
                            "fact_row_index": receipt.fact_row_index,
                            "stage_row_count": receipt.stage_row_count,
                            "fact_object_value": receipt.fact_object_value,
                            "source_binding_kind": receipt.source_binding_kind,
                            "source_subject_entity_id": (
                                receipt.source_subject_entity_id
                            ),
                            "source_property_id": receipt.source_property_id,
                            "source_qid_pid_sidecar_digest_sha256": (
                                receipt.source_qid_pid_sidecar_digest_sha256
                            ),
                            "stage_qid_pid_sidecar_digest_sha256": (
                                receipt.stage_qid_pid_sidecar_digest_sha256
                            ),
                            "proof_digest_sha256": receipt.proof_digest_sha256,
                        }
                        mutated = copy.deepcopy(receipt)
                        replacement_key = next(
                            key for key, _value in choices
                            if key != receipt.choice_key
                        )
                        object.__setattr__(mutated, "choice_key", replacement_key)
                        object.__setattr__(
                            mutated,
                            "proof_digest_sha256",
                            canonical_digest(mutated.proof_body()),
                        )
                        mutated.__post_init__()
                        output["mutation_rejected"] = not (
                            verify_generic_predicate_proof_receipt(
                                mutated,
                                stem,
                                compilation,
                                role_receipt=role,
                                context=context,
                            )
                        )
                except Exception as error:
                    output["error_kind"] = (
                        f"{type(error).__module__}.{type(error).__qualname__}"
                    )
                rows.append(output)
    payload = {
        "schema_version": SCHEMA,
        "frozen_commit": FROZEN_COMMIT,
        "candidate_input_sha256": _file_digest(input_path),
        "stage_bindings": bindings,
        "rows": rows,
    }
    output_path.write_bytes(_canonical_bytes(payload) + b"\n")


def _score(
    expected: dict[str, Any],
    worker: dict[str, Any],
    *,
    replay_equal: bool,
    candidate_digest: str,
    candidate_blobs: dict[str, str],
    before_inventory: list[dict[str, Any]],
    after_inventory: list[dict[str, Any]],
    source_digests_before: dict[str, str],
    source_digests_after: dict[str, str],
) -> dict[str, Any]:
    expected_rows = expected["expected_rows"]
    actual_rows = worker["rows"]
    if len(expected_rows) != len(actual_rows):
        raise RuntimeError("candidate row count does not match evaluator metadata")
    positives = [
        (row, actual_rows[row["line_index"]])
        for row in expected_rows
        if row["kind"] == "positive"
    ]
    negatives = [
        (row, actual_rows[row["line_index"]])
        for row in expected_rows
        if row["kind"] == "negative"
    ]
    invariants = [
        (row, actual_rows[row["line_index"]])
        for row in expected_rows
        if row["kind"] == "invariance_variant"
    ]
    positive_compiled = sum(actual["compiled"] for _expected, actual in positives)
    exact_subject_predicate = sum(
        actual["compiled"]
        and actual["goal_subject"] == gold["expected_subject"]
        and actual["goal_predicate"] == gold["expected_predicate"]
        for gold, actual in positives
    )
    wrong_compile = sum(
        actual["compiled"]
        and (
            actual["goal_subject"] != gold["expected_subject"]
            or actual["goal_predicate"] != gold["expected_predicate"]
        )
        for gold, actual in positives
    )
    verified_grounded = sum(
        actual["proof_verified"] and actual["grounded"]
        for _gold, actual in positives
    )
    exact_choice = sum(
        actual["choice_key"] == gold["expected_choice_key"]
        for gold, actual in positives
    )
    negative_firings = sum(actual["fired"] for _gold, actual in negatives)
    provenance_checks = []
    for _gold, actual in positives:
        proof = actual["proof"]
        if proof is None:
            continue
        common = (
            proof["predicate_namespace"] == "atanor.internal_graph"
            and proof["predicate_wikidata_property_id"] is None
            and proof["predicate_canonical_id"]
            == f"stage:{proof['predicate_name']}"
            and 0 <= proof["fact_row_index"] < proof["stage_row_count"]
        )
        if proof["stage_role"] == "literal":
            separated = (
                proof["source_binding_kind"] == "qid_pid_sidecar"
                and isinstance(proof["source_subject_entity_id"], str)
                and proof["source_subject_entity_id"].startswith("Q")
                and isinstance(proof["source_property_id"], str)
                and proof["source_property_id"].startswith("P")
                and proof["source_qid_pid_sidecar_digest_sha256"]
                == proof["stage_qid_pid_sidecar_digest_sha256"]
            )
        else:
            separated = (
                proof["source_binding_kind"] == "none"
                and proof["source_subject_entity_id"] is None
                and proof["source_property_id"] is None
                and proof["source_qid_pid_sidecar_digest_sha256"] is None
            )
        provenance_checks.append(common and separated)
    mutation_values = [
        actual["mutation_rejected"]
        for _gold, actual in positives
        if actual["mutation_rejected"] is not None
    ]
    invariance_values = []
    for gold, actual in invariants:
        baseline = actual_rows[gold["baseline_index"]]
        invariance_values.append(
            baseline["compiled"]
            and actual["compiled"]
            and baseline["goal_digest_sha256"] == actual["goal_digest_sha256"]
        )
    bounded_values = [
        actual["context_max_facts_per_stage"] == MAX_FACTS_PER_STAGE
        and actual["context_max_rows_examined_per_stage"] == MAX_ROWS_PER_STAGE
        and actual["context_fact_count"] <= MAX_FACTS_PER_STAGE * 2
        and actual["all_fact_rows_in_bounds"] is True
        for _gold, actual in positives
        if actual["context_status"] is not None
    ]
    failures = []
    for gold, actual in positives:
        failed = []
        if not actual["compiled"]:
            failed.append("not_compiled")
        if (
            actual["goal_subject"] != gold["expected_subject"]
            or actual["goal_predicate"] != gold["expected_predicate"]
        ):
            failed.append("subject_or_predicate_mismatch")
        if not (actual["proof_verified"] and actual["grounded"]):
            failed.append("proof_not_verified_grounded")
        if actual["choice_key"] != gold["expected_choice_key"]:
            failed.append("choice_key_mismatch")
        if actual["error_kind"] is not None:
            failed.append(f"worker_error:{actual['error_kind']}")
        if failed:
            failures.append(
                {
                    "line_index": gold["line_index"],
                    "subject": gold["expected_subject"],
                    "predicate": gold["expected_predicate"],
                    "failure_codes": failed,
                    "actual": actual,
                }
            )
    for gold, actual in negatives:
        if actual["fired"]:
            failures.append(
                {
                    "line_index": gold["line_index"],
                    "negative_category": gold["negative_category"],
                    "failure_codes": ["negative_fired"],
                    "actual": actual,
                }
            )
    filesystem_changed = before_inventory != after_inventory
    source_digest_changed = source_digests_before != source_digests_after
    metrics = {
        "positive_total": len(positives),
        "positive_exact_subject_predicate": exact_subject_predicate,
        "positive_exact_subject_predicate_rate": (
            exact_subject_predicate / len(positives)
        ),
        "compile_coverage": positive_compiled,
        "compile_coverage_rate": positive_compiled / len(positives),
        "proof_verified_and_grounded": verified_grounded,
        "proof_verified_and_grounded_rate": (
            verified_grounded / len(positives)
        ),
        "exact_choice_key": exact_choice,
        "wrong_compile": wrong_compile,
        "negative_total": len(negatives),
        "negative_final_firing": negative_firings,
        "provenance_pid_separation_checked": len(provenance_checks),
        "provenance_pid_separation_failures": (
            len(provenance_checks) - sum(provenance_checks)
        ),
        "mutation_rejection_checked": len(mutation_values),
        "mutation_rejection_failures": (
            len(mutation_values) - sum(mutation_values)
        ),
        "invariance_variants_checked": len(invariance_values),
        "invariance_failures": len(invariance_values) - sum(invariance_values),
        "bounded_contexts_checked": len(bounded_values),
        "bounded_context_failures": len(bounded_values) - sum(bounded_values),
        "deterministic_replay_equal": replay_equal,
        "filesystem_no_write_delta": not filesystem_changed,
        "critical_source_digest_no_write_delta": not source_digest_changed,
    }
    gates = {
        "positive_exact_subject_predicate": (
            exact_subject_predicate == len(positives)
        ),
        "compile_coverage": positive_compiled == len(positives),
        "proof_verified_grounded": verified_grounded == len(positives),
        "wrong_compile_zero": wrong_compile == 0,
        "negative_final_firing_zero": negative_firings == 0,
        "provenance_pid_separation": (
            bool(provenance_checks) and all(provenance_checks)
        ),
        "mutation_rejection": bool(mutation_values) and all(mutation_values),
        "choice_order_distractor_goal_digest_invariance": (
            len(invariance_values) == len(positives) * 2
            and all(invariance_values)
        ),
        "deterministic_replay": replay_equal,
        "bounded_rows": bool(bounded_values) and all(bounded_values),
        "source_candidate_dataset_digests_present": all(
            (
                candidate_digest,
                worker["candidate_input_sha256"],
                worker["stage_bindings"][0]["stage_digest_sha256"],
                worker["stage_bindings"][1]["stage_digest_sha256"],
            )
        ),
        "filesystem_no_write_delta": (
            not filesystem_changed and not source_digest_changed
        ),
    }
    return {
        "schema_version": SCHEMA,
        "measurement_class": "unsigned_source_separated_self_measurement",
        "authority_disclaimer": {
            "external_evaluation": False,
            "external_authenticity": False,
            "independent_evaluation": False,
            "e4": False,
            "e5": False,
            "capability_claim": False,
        },
        "frozen_candidate": {
            "commit": FROZEN_COMMIT,
            "candidate_source_digest_sha256": candidate_digest,
            "candidate_surface_blob_sha256": candidate_blobs,
        },
        "dataset": {
            "salt": SALT,
            "candidate_input_path": INPUT_PATH.relative_to(REPO).as_posix(),
            "candidate_input_sha256": worker["candidate_input_sha256"],
            "evaluator_expected_path": EXPECTED_PATH.relative_to(REPO).as_posix(),
            "evaluator_expected_sha256": _file_digest(EXPECTED_PATH),
            "positive_count": expected["positive_count"],
            "negative_count": expected["negative_count"],
            "invariance_variant_count": expected["invariance_variant_count"],
            "predicate_counts": expected["predicate_counts"],
            "answer_position_counts": expected["answer_position_counts"],
            "negative_category_counts": expected["negative_category_counts"],
        },
        "sources": {
            "stage_bindings": worker["stage_bindings"],
            "critical_source_digests_before": source_digests_before,
            "critical_source_digests_after": source_digests_after,
            "source_binding_digest_sha256": _digest(worker["stage_bindings"]),
        },
        "metrics": metrics,
        "gates": gates,
        "gate_pass": all(gates.values()),
        "failures": failures,
        "filesystem_delta": {
            "before_inventory_sha256": _digest(before_inventory),
            "after_inventory_sha256": _digest(after_inventory),
            "changed": filesystem_changed,
            "before_file_count": len(before_inventory),
            "after_file_count": len(after_inventory),
        },
        "replay": {
            "run1_path": WORKER1_PATH.relative_to(REPO).as_posix(),
            "run1_sha256": _file_digest(WORKER1_PATH),
            "run2_path": WORKER2_PATH.relative_to(REPO).as_posix(),
            "run2_sha256": _file_digest(WORKER2_PATH),
            "byte_equal": replay_equal,
        },
    }


def _write_candidate_inputs(candidates: list[dict[str, Any]]) -> None:
    with INPUT_PATH.open("wb") as handle:
        for item in candidates:
            if set(item) != {"stem", "choices"}:
                raise RuntimeError("candidate input contains evaluator metadata")
            handle.write(_canonical_bytes(item) + b"\n")


def _run() -> None:
    for path in (INPUT_PATH, EXPECTED_PATH, WORKER1_PATH, WORKER2_PATH, RECEIPT_PATH):
        if path.exists():
            raise FileExistsError(
                f"one-shot artifact already exists; refusing to overwrite: {path}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    if (
        plan["salt"] != SALT
        or plan["frozen_candidate_commit"] != FROZEN_COMMIT
    ):
        raise RuntimeError("predeclared plan does not match evaluator constants")
    candidate_digest, candidate_blobs = _candidate_digest_and_freeze_check()
    candidates, expected = _build_dataset()
    _write_candidate_inputs(candidates)
    EXPECTED_PATH.write_bytes(_canonical_bytes(expected) + b"\n")
    before_inventory = _inventory((B1_ROOT, S1_ROOT))
    source_before = _critical_source_digests()
    environment = dict(os.environ)
    environment["PYTHONHASHSEED"] = "0"
    for output_path in (WORKER1_PATH, WORKER2_PATH):
        subprocess.run(
            (
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker",
                str(INPUT_PATH),
                str(output_path),
            ),
            cwd=REPO,
            env=environment,
            check=True,
        )
    after_inventory = _inventory((B1_ROOT, S1_ROOT))
    source_after = _critical_source_digests()
    replay_equal = WORKER1_PATH.read_bytes() == WORKER2_PATH.read_bytes()
    worker = json.loads(WORKER1_PATH.read_text(encoding="utf-8"))
    receipt = _score(
        expected,
        worker,
        replay_equal=replay_equal,
        candidate_digest=candidate_digest,
        candidate_blobs=candidate_blobs,
        before_inventory=before_inventory,
        after_inventory=after_inventory,
        source_digests_before=source_before,
        source_digests_after=source_after,
    )
    RECEIPT_PATH.write_bytes(_canonical_bytes(receipt) + b"\n")
    print(
        json.dumps(
            {
                "receipt": str(RECEIPT_PATH),
                "gate_pass": receipt["gate_pass"],
                "metrics": receipt["metrics"],
            },
            indent=2,
            sort_keys=True,
        )
    )


def _resume_existing() -> None:
    """Resume only the exact artifacts emitted before the worker import incident."""

    for path in (INPUT_PATH, EXPECTED_PATH, PLAN_PATH):
        if not path.is_file():
            raise FileNotFoundError(f"resume artifact is unavailable: {path}")
    if _file_digest(INPUT_PATH) != RESUME_INPUT_SHA256:
        raise RuntimeError("resume candidate input hash does not match")
    if _file_digest(EXPECTED_PATH) != RESUME_EXPECTED_SHA256:
        raise RuntimeError("resume evaluator expected hash does not match")
    for path in (WORKER1_PATH, WORKER2_PATH, RECEIPT_PATH, INCIDENT_PATH):
        if path.exists():
            raise FileExistsError(
                f"resume refuses to overwrite an existing artifact: {path}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    if (
        plan["salt"] != SALT
        or plan["frozen_candidate_commit"] != FROZEN_COMMIT
    ):
        raise RuntimeError("predeclared plan does not match resume constants")
    expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    if (
        expected["salt"] != SALT
        or expected["positive_count"] != 84
        or expected["negative_count"] != 30
        or expected["invariance_variant_count"] != 168
    ):
        raise RuntimeError("resume evaluator metadata contract does not match")
    incident = {
        "schema_version": "atanor.a2.stage5.evaluator-incident.v1",
        "phase": "worker_import_before_candidate",
        "error_kind": "builtins.ModuleNotFoundError",
        "candidate_calls": 0,
        "candidate_input_sha256": RESUME_INPUT_SHA256,
        "evaluator_expected_sha256": RESUME_EXPECTED_SHA256,
        "dataset_regenerated": False,
        "dataset_resampled": False,
        "candidate_changed": False,
        "resume_action": "repository_sys_path_bootstrap_only",
    }
    INCIDENT_PATH.write_bytes(_canonical_bytes(incident) + b"\n")
    candidate_digest, candidate_blobs = _candidate_digest_and_freeze_check()
    before_inventory = _inventory((B1_ROOT, S1_ROOT))
    source_before = _critical_source_digests()
    environment = dict(os.environ)
    environment["PYTHONHASHSEED"] = "0"
    for output_path in (WORKER1_PATH, WORKER2_PATH):
        subprocess.run(
            (
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker",
                str(INPUT_PATH),
                str(output_path),
            ),
            cwd=REPO,
            env=environment,
            check=True,
        )
    after_inventory = _inventory((B1_ROOT, S1_ROOT))
    source_after = _critical_source_digests()
    replay_equal = WORKER1_PATH.read_bytes() == WORKER2_PATH.read_bytes()
    worker = json.loads(WORKER1_PATH.read_text(encoding="utf-8"))
    receipt = _score(
        expected,
        worker,
        replay_equal=replay_equal,
        candidate_digest=candidate_digest,
        candidate_blobs=candidate_blobs,
        before_inventory=before_inventory,
        after_inventory=after_inventory,
        source_digests_before=source_before,
        source_digests_after=source_after,
    )
    receipt["execution_disclosure"] = {
        "initial_incident_path": INCIDENT_PATH.relative_to(REPO).as_posix(),
        "initial_incident_sha256": _file_digest(INCIDENT_PATH),
        "initial_candidate_calls": 0,
        "resumed_from_exact_existing_artifacts": True,
        "candidate_input_sha256_verified": RESUME_INPUT_SHA256,
        "evaluator_expected_sha256_verified": RESUME_EXPECTED_SHA256,
        "dataset_regenerated": False,
        "dataset_resampled": False,
        "candidate_changed": False,
        "plumbing_change": "repository_sys_path_bootstrap_only",
    }
    RECEIPT_PATH.write_bytes(_canonical_bytes(receipt) + b"\n")
    print(
        json.dumps(
            {
                "receipt": str(RECEIPT_PATH),
                "gate_pass": receipt["gate_pass"],
                "metrics": receipt["metrics"],
            },
            indent=2,
            sort_keys=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", nargs=2, metavar=("INPUT", "OUTPUT"))
    parser.add_argument("--resume-existing", action="store_true")
    arguments = parser.parse_args()
    if arguments.worker:
        input_path, output_path = (Path(value).resolve() for value in arguments.worker)
        _worker(input_path, output_path)
    elif arguments.resume_existing:
        _resume_existing()
    else:
        _run()


if __name__ == "__main__":
    main()
