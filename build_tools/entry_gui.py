# -*- coding: utf-8 -*-
"""PyInstaller entry point — SwitchLoc desktop app (GUI).

Thin launcher with absolute imports (required for frozen builds).
The PyInstaller splash screen (created with --splash in BUILD.bat) is
visible from the very first millisecond of the exe; the app closes it
in `main_window.launch()` once the Qt interface is ready.
"""
import sys


def _boot_text(msg: str) -> None:
    """Update the PyInstaller splash text if the bootloader provides it."""
    try:
        import pyi_splash
        if pyi_splash.is_alive():
            pyi_splash.update_text(msg)
    except Exception:
        pass


def _fatal(exc: BaseException) -> None:
    """Start-up failure before the Qt window exists (e.g. a missing DLL):
    the windowed exe has no console, so log it and show a native box."""
    import traceback
    text = "".join(traceback.format_exception(type(exc), exc,
                                              exc.__traceback__))
    where = "(log unavailable)"
    try:
        from switchloc.logging_setup import get_logger, log_path_text
        get_logger("boot").critical("start-up failure:\n%s", text)
        where = log_path_text()
    except Exception:                                   # noqa: BLE001
        pass
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0, f"{type(exc).__name__}: {exc}\n\nDetails: {where}",
            "SwitchLoc — cannot start", 0x10)
    except Exception:                                   # noqa: BLE001
        sys.stderr.write(text)


def main() -> int:
    _boot_text("SwitchLoc — loading…")
    try:
        from switchloc.ui.qt.main_window import launch
        return launch(sys.argv[1] if len(sys.argv) > 1 else None)
    except Exception as exc:                            # noqa: BLE001
        _fatal(exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
