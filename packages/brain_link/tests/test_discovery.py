# -*- coding: utf-8 -*-
"""ND-1: resolve peers by AI-ID, not IP. Adverts self-certifying; rendezvous untrusted; hijack,
forgery, and rollback all refused."""
from packages.brain_link.discovery import (Advert, LocalFileRendezvous, advert_is_authentic,
                                           make_advert)
from packages.brain_link.protocol import generate_identity


def _rv(tmp_path):
    return LocalFileRendezvous(tmp_path / "rendezvous.json")


def test_publish_and_resolve_by_ai_id(tmp_path):
    pub, sec = generate_identity()
    rv = _rv(tmp_path)
    assert rv.publish(make_advert("atanor-edge", pub, sec, "drop://cloud/atanor-edge", ts=100.0))
    a = rv.resolve("atanor-edge")
    assert a is not None and a.endpoint == "drop://cloud/atanor-edge" and a.pubkey == pub
    assert advert_is_authentic(a)                          # the resolver verifies, not trusts


def test_forged_advert_rejected_at_publish_and_read(tmp_path):
    pub, sec = generate_identity()
    rv = _rv(tmp_path)
    a = make_advert("atanor-x", pub, sec, "drop://cloud/x", ts=1.0)
    a.endpoint = "drop://evil/relay"                       # tampered after signing
    assert rv.publish(a) is False                          # refused at publish
    assert rv.resolve("atanor-x") is None


def test_ai_id_cannot_be_hijacked_by_another_key(tmp_path):
    pub1, sec1 = generate_identity()
    pub2, sec2 = generate_identity()
    rv = _rv(tmp_path)
    assert rv.publish(make_advert("atanor-edge", pub1, sec1, "drop://a", ts=1.0))
    # attacker with a DIFFERENT key tries to claim the same AI-ID
    assert rv.publish(make_advert("atanor-edge", pub2, sec2, "drop://evil", ts=2.0)) is False
    assert rv.resolve("atanor-edge").pubkey == pub1        # first binding stands


def test_stale_advert_rollback_refused(tmp_path):
    pub, sec = generate_identity()
    rv = _rv(tmp_path)
    assert rv.publish(make_advert("atanor-edge", pub, sec, "drop://new", ts=200.0))
    assert rv.publish(make_advert("atanor-edge", pub, sec, "drop://old", ts=100.0)) is False
    assert rv.resolve("atanor-edge").endpoint == "drop://new"
