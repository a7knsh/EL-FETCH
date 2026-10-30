"""Build standalone executables with PyInstaller (run on the target OS – Windows builds need Windows).

    python scripts/build.py          # CLI + GUI
    python scripts/build.py cli      # only the terminal version
    python scripts/build.py gui      # only the GUI

Output: dist/elfetch(.exe) and dist/elfetch-gui(.exe)
"""
from __future__ import annotations

import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent.parent
EXCLUDE = ["playwright", "tkinter", "matplotlib", "numpy", "PySide6.QtWebEngineCore", "PySide6.Qt3DCore", "PySide6.QtQuick"]


def build(name: str, entry: str, windowed: bool, extra: list[str]) -> None:
    args = [
        str(ROOT / "scripts" / entry),
        "--name", name,
        "--onefile",
        "--noconfirm",
        "--clean",
        "--paths", str(ROOT),
        "--collect-data", "elfetch",          # data/shipping.toml
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
        *(f"--exclude-module={m}" for m in EXCLUDE),
        *extra,
    ]
    if windowed:
        args.append("--windowed")
    PyInstaller.__main__.run(args)


def main() -> None:
    what = sys.argv[1:] or ["cli", "gui"]
    if "cli" in what:
        build("elfetch", "entry_cli.py", False, ["--exclude-module=PySide6"])
    if "gui" in what:
        build("elfetch-gui", "entry_gui.py", True, [])
    print("\nDone – executables are in", ROOT / "dist")


if __name__ == "__main__":
    main()
