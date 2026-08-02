from trainer import run_dry_run


def test_dry_run_writes_checkpoint(tmp_path):
    cleaned = tmp_path / "cleaned"
    cleaned.mkdir()
    (cleaned / "doc.txt").write_text("ATANOR training dry run sample text.", encoding="utf-8")

    result = run_dry_run(str(cleaned), str(tmp_path / "sample"), str(tmp_path / "ckpt"), steps=3)

    assert result["state"] == "completed"
    assert len(result["losses"]) == 3
    assert (tmp_path / "ckpt" / "manifest.json").exists()
