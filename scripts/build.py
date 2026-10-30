"""Build the standalone app with PyInstaller (run on the target OS – a Windows build needs Windows).

    pip install -e '.[gui,dev]'
    python scripts/build.py

Output: dist/EL-FETCH (Linux) or dist/EL-FETCH.exe (Windows). One file: double-click opens the
window, `EL-FETCH search …` in a terminal runs the CLI.
"""
from __future__ import annotations

import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent.parent
EXCLUDE = [
    "playwright", "tkinter", "matplotlib", "numpy",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick",
    "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.QtCharts", "PySide6.QtDataVisualization",
]


def main() -> None:
    args = [
        str(ROOT / "scripts" / "launch.py"),
        "--name", "EL-FETCH",
        "--onefile",
        "--noconfirm",
        "--clean",
        "--paths", str(ROOT),
        "--collect-data", "elfetch",          # shipping.toml, icon.png
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
        *(f"--exclude-module={m}" for m in EXCLUDE),
    ]
    if sys.platform == "win32":
        # console exe so the CLI works from cmd/PowerShell; the console is dropped on double-click
        args += ["--icon", str(ROOT / "packaging" / "icon.ico")]
    PyInstaller.__main__.run(args)
    print("\nDone –", ROOT / "dist" / ("EL-FETCH.exe" if sys.platform == "win32" else "EL-FETCH"))


if __name__ == "__main__":
    main()
