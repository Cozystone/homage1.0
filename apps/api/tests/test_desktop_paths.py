from __future__ import annotations

from app.services.database import homage_memory_db_path
from app.services.desktop_paths import configure_desktop_data_dir


def test_desktop_data_dir_keeps_sqlite_out_of_install_folder(tmp_path, monkeypatch) -> None:
    install_dir = tmp_path / "install"
    data_dir = tmp_path / "appdata" / "Homage"
    install_dir.mkdir()
    monkeypatch.chdir(install_dir)
    monkeypatch.setenv("HOMAGE_DATA_DIR", str(data_dir))

    configured = configure_desktop_data_dir(chdir=False)
    db_path = homage_memory_db_path()

    assert configured == data_dir.resolve()
    assert db_path == data_dir.resolve() / "data" / "memory" / "homage_memory.sqlite3"
    assert install_dir not in db_path.parents
