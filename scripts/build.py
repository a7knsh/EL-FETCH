"""Build the standalone app with PyInstaller (run on the target OS – a Windows build needs Windows).

    pip install -e '.[gui,dev]'
    python scripts/build.py              # one-file app
    python scripts/build.py --appimage   # Linux: EL-FETCH-x86_64.AppImage (needs appimagetool on PATH or $APPIMAGETOOL)

Output: dist/EL-FETCH (Linux) or dist/EL-FETCH.exe (Windows). One file: double-click opens the
window, `EL-FETCH search …` in a terminal runs the CLI.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent.parent
EXCLUDE = [
    "playwright", "tkinter", "matplotlib", "numpy",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick",
    "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.QtCharts", "PySide6.QtDataVisualization",
]
DESKTOP = """[Desktop Entry]
Type=Application
Name=EL-FETCH
Comment=Find the cheapest electronics parts incl. shipping
Exec=EL-FETCH
Icon=elfetch
Terminal=false
Categories=Utility;
"""


def pyinstaller(onefile: bool, distpath: Path) -> None:
    args = [
        str(ROOT / "scripts" / "launch.py"),
        "--name", "EL-FETCH",
        "--onefile" if onefile else "--onedir",
        "--noconfirm",
        "--clean",
        "--paths", str(ROOT),
        "--collect-data", "elfetch",          # shipping.toml, icon.png
        "--distpath", str(distpath),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
        *(f"--exclude-module={m}" for m in EXCLUDE),
    ]
    if sys.platform == "win32":
        # console exe so the CLI works from cmd/PowerShell; the console is dropped on double-click
        args += ["--icon", str(ROOT / "packaging" / "icon.ico")]
    PyInstaller.__main__.run(args)


def appimage() -> Path:
    """Unpacked (onedir) build inside an AppDir, so it starts fast – no second extraction step."""
    tool = os.environ.get("APPIMAGETOOL") or shutil.which("appimagetool")
    if not tool:
        sys.exit("appimagetool not found: put it on PATH or set APPIMAGETOOL")
    appdir = ROOT / "build" / "EL-FETCH.AppDir"
    shutil.rmtree(appdir, ignore_errors=True)
    pyinstaller(onefile=False, distpath=appdir / "usr" / "lib")
    (appdir / "AppRun").symlink_to("usr/lib/EL-FETCH/EL-FETCH")
    (appdir / "elfetch.desktop").write_text(DESKTOP, encoding="utf-8")
    shutil.copy(ROOT / "elfetch" / "data" / "icon.png", appdir / "elfetch.png")
    (appdir / ".DirIcon").symlink_to("elfetch.png")
    out = ROOT / "dist" / "EL-FETCH-x86_64.AppImage"
    out.parent.mkdir(exist_ok=True)
    subprocess.run([tool, "--no-appstream", str(appdir), str(out)], check=True,
                   env={**os.environ, "ARCH": "x86_64", "APPIMAGE_EXTRACT_AND_RUN": "1"})
    return out


def main() -> None:
    if "--appimage" in sys.argv:
        print("\nDone –", appimage())
        return
    pyinstaller(onefile=True, distpath=ROOT / "dist")
    print("\nDone –", ROOT / "dist" / ("EL-FETCH.exe" if sys.platform == "win32" else "EL-FETCH"))


if __name__ == "__main__":
    main()
