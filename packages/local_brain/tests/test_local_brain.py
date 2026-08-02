from __future__ import annotations

from packages.local_brain import LocalBrainMemory, extract_user_facts


def test_extracts_korean_name_and_preference():
    facts = extract_user_facts("내 이름은 블루야. 나는 커피를 좋아해", "ko")
    by_subject = {s: v for _k, s, v, _c in facts}
    assert by_subject.get("name") == "블루"

    assert by_subject.get("likes") == "커피"


def test_extracts_english_name_and_like():
    facts = extract_user_facts("My name is Blue and I like jazz.", "en")
    by_subject = {s: v for _k, s, v, _c in facts}
    assert by_subject.get("name") == "Blue"
    assert "jazz" in by_subject.get("likes", "")


def test_question_turn_does_not_pollute_facts():

    assert extract_user_facts("내가 뭘 좋아한다고 했지?", "ko") == []
    assert extract_user_facts("what do I like again?", "en") == []


def test_never_extracts_sensitive():
    assert extract_user_facts("my password is hunter2", "en") == []
    assert extract_user_facts("내 비밀번호는 1234야", "ko") == []


def test_memory_remember_dedup_and_recall(tmp_path):
    mem = LocalBrainMemory(tmp_path / "mem.json")
    mem.remember("identity", "name", "Blue")
    mem.remember("preference", "likes", "coffee")
    mem.remember("identity", "name", "Bluey")  # update, not duplicate

    assert mem.status()["total_facts"] == 2
    recalled = mem.recall("what is my name")
    assert any(f.subject == "name" and f.value == "Bluey" for f in recalled)


def test_memory_persists_across_instances(tmp_path):
    path = tmp_path / "mem.json"
    LocalBrainMemory(path).remember("preference", "likes", "tea")
    reloaded = LocalBrainMemory(path)
    assert reloaded.status()["total_facts"] == 1
    assert reloaded.recall("tea")[0].value == "tea"


def test_import_graph_hub_persona_source(tmp_path):
    mem = LocalBrainMemory(tmp_path / "mem.json")
    added = mem.import_graph_hub_source(
        "warm_mentor_v1",
        "persona",
        [{"subject": "tone", "value": "warm and encouraging"}, {"subject": "style", "value": "concise"}],
    )
    assert len(added) == 2
    assert all(f.source == "graph_hub" for f in added)
    assert mem.status()["by_kind"].get("persona") == 2
    assert mem.status()["by_source"].get("graph_hub") == 2


def test_status_marks_private_and_no_cloud(tmp_path):
    status = LocalBrainMemory(tmp_path / "mem.json").status()
    assert status["private_on_device"] is True
    assert status["uploaded_to_cloud"] is False
    assert status["production_store_mutated"] is False


def test_max_facts_evicts_oldest(tmp_path):
    mem = LocalBrainMemory(tmp_path / "capped.json", max_facts=3)
    for i in range(5):
        mem.remember("knowledge", f"topic{i}", f"value{i}")
    assert mem.status()["total_facts"] == 3
    subjects = {f.subject for f in mem.all_facts()}
    # the two oldest (topic0, topic1) were evicted; the newest remain
    assert subjects == {"topic2", "topic3", "topic4"}


def test_no_cap_keeps_everything(tmp_path):
    mem = LocalBrainMemory(tmp_path / "uncapped.json")  # no max_facts
    for i in range(10):
        mem.remember("knowledge", f"t{i}", f"v{i}")
    assert mem.status()["total_facts"] == 10
