"""One entry point for everything: no arguments opens the GUI, any arguments run the terminal version.

    EL-FETCH                    # double-click / start menu -> window
    EL-FETCH search 1N4007      # terminal
"""
from __future__ import annotations

import os
import sys


def _detach_console_if_double_clicked() -> None:
    """On Windows the exe is a console program (so the CLI works). When it was started by
    double-click it owns a fresh console window nobody wants – drop it before the GUI opens."""
    if os.name != "nt":
        return
    import ctypes
    k = ctypes.windll.kernel32
    if k.GetConsoleWindow() and k.GetConsoleProcessList((ctypes.c_uint * 2)(), 2) <= 1:
        k.FreeConsole()


def run_gui() -> None:
    try:
        from .gui.app import main as gui_main
    except ImportError:
        print("The GUI needs PySide6:  pip install 'elfetch[gui]'\n"
              "Use the terminal version instead, e.g.:  elfetch search 1N4007", file=sys.stderr)
        sys.exit(1)
    _detach_console_if_double_clicked()
    gui_main()


def main() -> None:
    if len(sys.argv) <= 1:
        run_gui()
        return
    from .cli.main import app
    app()


if __name__ == "__main__":
    main()
