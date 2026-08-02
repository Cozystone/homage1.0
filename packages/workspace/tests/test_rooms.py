# -*- coding: utf-8 -*-
"""Rooms — the rules a room actually enforces, and the loss they exist to prevent.

Written the same day the reachability census listed `workspace` as a true orphan: no API caller, no
script, no test. The first suture on that list is the author's own, and an untested module is not a
capability — it is a claim about one.

The load-bearing test is the append-only one. Hours after rooms.py was written, an E5 measurement
record was overwritten by a later run writing the same fixed path, and the record survived only
because it had also been copied into a document. That is precisely what a ledger room refuses, in a
place that was not using one.
"""
from __future__ import annotations

import pytest

from packages.workspace.rooms import KINDS, Rooms, RoomError


def _rooms(tmp_path):
    return Rooms(manifest=tmp_path / "manifest.json")


def test_a_ledger_refuses_to_overwrite_its_own_record():
    """The failure this module was built for, reproduced. A ledger entry is added, never replaced,
    because losing the record costs the record itself."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        r = Rooms(manifest=Path(td) / "manifest.json")
        r.declare("measurements", kind="ledger", purpose="sealed run outputs",
                  path=str(Path(td) / "measurements"))
        p = r.place("measurements", "run_1.json")
        p.write_text("{}", encoding="utf-8")
        with pytest.raises(RoomError) as e:
            r.place("measurements", "run_1.json")
        assert "append-only" in str(e.value)


def test_the_vault_is_not_reachable_through_this_api_at_all():
    """Not an oversight — the containment. A general file helper that knew the way into the vault
    would be a path from every caller to the secrets."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        r = Rooms(manifest=Path(td) / "manifest.json")
        r.declare("secrets", kind="vault", purpose="keys", path=str(Path(td) / "secrets"))
        with pytest.raises(RoomError) as e:
            r.place("secrets", "key.pem")
        assert "not reachable" in str(e.value)


def test_a_room_must_say_what_it_is_for():
    """`data/perception/` collected four unrelated files because no room ever had to state a purpose,
    so nothing could say a file did not belong."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        r = Rooms(manifest=Path(td) / "manifest.json")
        with pytest.raises(RoomError):
            r.declare("nameless", kind="scratch", purpose="   ")


def test_a_kind_cannot_be_changed_out_from_under_an_existing_room():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        r = Rooms(manifest=Path(td) / "manifest.json")
        r.declare("ledger_a", kind="ledger", purpose="records", path=str(Path(td) / "a"))
        with pytest.raises(RoomError):
            r.declare("ledger_a", kind="scratch", purpose="records")


def test_rewritable_rooms_allow_rewriting():
    """The opposite case. If every room were append-only the API would be unusable and callers would
    route around it, which is how a rule becomes decorative."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        r = Rooms(manifest=Path(td) / "manifest.json")
        r.declare("work", kind="derived", purpose="rebuildable indexes", path=str(Path(td) / "work"))
        p = r.place("work", "index.json")
        p.write_text("1", encoding="utf-8")
        assert r.place("work", "index.json") == p          # no refusal


def test_every_kind_declares_what_losing_it_costs():
    """The axis the whole module exists for: lifecycle, not topic. A kind that could not say what its
    loss costs would not be answering the question rooms were built to answer."""
    for kind, rules in KINDS.items():
        assert "loss" in rules and rules["loss"]
        assert isinstance(rules["rebuildable"], bool)


def test_room_of_resolves_the_longest_matching_path():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        r = Rooms(manifest=Path(td) / "manifest.json")
        r.declare("outer", kind="derived", purpose="outer", path="data/x")
        r.declare("inner", kind="ledger", purpose="inner", path="data/x/y")
        assert r.room_of("data/x/y/file.json").name == "inner"
        assert r.room_of("data/x/other.json").name == "outer"
        assert r.room_of("data/unclaimed/f.json") is None
