from packages.hermes_intake.license_check import detect_license


def test_detect_mit_license(tmp_path):
    (tmp_path / "LICENSE").write_text("MIT License\nPermission is hereby granted, free of charge.\n", encoding="utf-8")
    info = detect_license(tmp_path)
    assert info["license_file_present"] is True
    assert info["license_detected"] == "MIT"
    assert info["mit_compatible"] is True
