from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "apps" / "api" / "app" / "desktop_entry.py"
BINARIES_DIR = ROOT / "src-tauri" / "binaries"
RAW_DIST = ROOT / "build" / "pyinstaller" / "dist"
WORK_DIR = ROOT / "build" / "pyinstaller" / "work"
SPEC_DIR = ROOT / "build" / "pyinstaller" / "spec"
BASE_NAME = "homage-api"


# Every package root the backend can import. The app pulls in many cross-package deps
# (e.g. cloud_brain -> seed_research) and several packages add themselves to sys.path at
# RUNTIME (sys.path.insert), which PyInstaller's static analysis cannot follow — so a
# hand-curated subset silently drops modules and the sidecar crashes at launch.
#
# Mirror the EXACT search roots the running engine has (repo root + every packages/* dir,
# per start_atanor_after_reboot.ps1's PYTHONPATH). Crucially do NOT add packages/ itself:
# some packages are self-vendoring shims (e.g. packages/seed_research/__init__.py re-exports
# the inner packages/seed_research/seed_research via a runtime sys.path.insert). With
# packages/seed_research on the path, `import seed_research` resolves to the inner REAL
# package; adding packages/ instead resolves to the outer shim, which then re-imports itself
# and yields an empty module ("cannot import name ... from seed_research.*"). --paths only
# enables resolution; bundle size is set by the actual import graph from app.main.
_PACKAGES_DIR = ROOT / "packages"
PACKAGE_PATHS = [
    ROOT,
    ROOT / "apps" / "api",
    *sorted(
        p for p in _PACKAGES_DIR.iterdir()
        if p.is_dir() and not p.name.startswith((".", "__"))
    ),
]


# Heavy ML/data libraries that are installed in the dev env but NOT needed by the
# no-LLM, numpy-based ATANOR backend. They are only ever imported lazily (e.g. an
# optional torch GPU probe in neuro_efficiency, guarded by try/except), never at
# module load. Excluding them drops the onefile sidecar from ~3 GB to a few hundred
# MB — small enough for the NSIS installer to mmap (the --onefile + 3 GB combo was
# what broke `makensis`). kiwipiepy (Korean morphology) is kept; it is required.
EXCLUDE_MODULES = [
    "torch", "torchvision", "torchaudio",
    "tensorflow", "tensorboard",
    "transformers", "tokenizers", "safetensors",
    "scipy", "sklearn", "pandas", "matplotlib",
    "IPython", "notebook", "jupyter",
]


HIDDEN_IMPORTS = [
    "app.main",
    "app.desktop_entry",
    "app.routers.cloud_brain",
    "app.routers.datagate",
    "app.routers.factory",
    "app.routers.graphrag",
    "app.routers.guard",
    "app.routers.harvest",
    "app.routers.hybrid_network",
    "app.routers.learning",
    "app.routers.memory",
    "app.routers.neuro",
    "app.routers.ontology",
    "app.routers.oven",
    "app.routers.telemetry",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
]


def run(command: list[str], *, cwd: Path = ROOT) -> str:
    completed = subprocess.run(command, cwd=cwd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return completed.stdout


def target_triple() -> str:
    override = os.getenv("TAURI_TARGET_TRIPLE")
    if override:
        return override
    try:
        output = run(["rustc", "-vV"])
        for line in output.splitlines():
            if line.startswith("host:"):
                return line.split(":", 1)[1].strip()
    except Exception:
        machine = platform.machine().lower()
        system = platform.system().lower()
        arch = "aarch64" if machine in {"arm64", "aarch64"} else "x86_64"
        if system == "windows":
            return f"{arch}-pc-windows-msvc"
        if system == "darwin":
            return f"{arch}-apple-darwin"
        return f"{arch}-unknown-linux-gnu"
    raise RuntimeError("could not determine target triple")


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller.__main__  # type: ignore  # noqa: F401
    except Exception as exc:
        raise RuntimeError("PyInstaller is required. Install it with `python -m pip install pyinstaller`.") from exc


def build() -> Path:
    ensure_pyinstaller()
    BINARIES_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    SPEC_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIST.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(ENTRYPOINT),
        "--name",
        BASE_NAME,
        "--onefile",
        "--clean",
        "--noconfirm",
        "--distpath",
        str(RAW_DIST),
        "--workpath",
        str(WORK_DIR),
        "--specpath",
        str(SPEC_DIR),
    ]
    for path in PACKAGE_PATHS:
        command.extend(["--paths", str(path)])
    for name in HIDDEN_IMPORTS:
        command.extend(["--hidden-import", name])
    for name in EXCLUDE_MODULES:
        command.extend(["--exclude-module", name])
    run(command)

    suffix = ".exe" if platform.system().lower() == "windows" else ""
    built = RAW_DIST / f"{BASE_NAME}{suffix}"
    if not built.exists():
        raise FileNotFoundError(f"PyInstaller output not found: {built}")
    target = BINARIES_DIR / f"{BASE_NAME}-{target_triple()}{suffix}"
    if target.exists():
        target.unlink()
    shutil.copy2(built, target)
    print(f"Built sidecar: {target}")
    return target


if __name__ == "__main__":
    build()
