from __future__ import annotations

from packages.runtime_control.stop_marker import (
    check_stop_requested,
    clear_stop_marker,
    create_stop_marker,
    marker_path,
    read_stop_reason,
)


def test_stop_marker_create_read_clear(tmp_path):
    marker = create_stop_marker(
        "run_fixture",
        "user_stop_requested",
        stop_dir=tmp_path,
        metadata={"source": "test"},
    )

    assert marker.reason == "user_stop_requested"
    assert marker_path("run_fixture", tmp_path).exists()
    assert check_stop_requested("run_fixture", stop_dir=tmp_path) is True

    read = read_stop_reason("run_fixture", stop_dir=tmp_path)
    assert read is not None
    assert read.run_id == "run_fixture"
    assert read.metadata == {"source": "test"}

    assert clear_stop_marker("run_fixture", stop_dir=tmp_path) is True
    assert check_stop_requested("run_fixture", stop_dir=tmp_path) is False


def test_stop_marker_rejects_path_escape(tmp_path):
    try:
        create_stop_marker("../bad", "stop", stop_dir=tmp_path)
    except ValueError as exc:
        assert "path-safe" in str(exc)
    else:
        raise AssertionError("expected ValueError")
