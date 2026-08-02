from packages.agentic_micro_os.splatra_cell import SplatraCosmosCell


def test_splatra_cell_limits_and_patch_proposal():
    cell = SplatraCosmosCell()
    assert cell.path_allowed("packages/splatra_turbovec/codec.py") is True
    assert cell.path_allowed("../escape.py") is False
    proposal = cell.propose_orb_patch("proposal only")
    assert proposal.requires_human_approval is True
    controls = cell.map_emotion_to_visual_controls(0.5, 1.0, 0.3)
    assert controls["shell_ripple_amplitude"] > 0
