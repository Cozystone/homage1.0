from packages.agentic_micro_os.virtual_fs import validate_cell_path


def test_path_traversal_rejected():
    assert validate_cell_path("../secret", ["packages/splatra_turbovec"]) is False
    assert validate_cell_path("packages/splatra_turbovec/codec.py", ["packages/splatra_turbovec"]) is True
