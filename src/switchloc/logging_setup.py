# -*- coding: utf-8 -*-
"""Central logging — one rotating log file in a per-user writable folder.

Why: the old design appended raw tracebacks to ``switchloc_run_log.txt``
in the current directory (often read-only or inside the shipped folder,
and it ended up inside the release archive with developer paths).

* ``SWITCHLOC_LOG_DIR`` env var overrides the location.
* Windows: ``%LOCALAPPDATA%/SwitchLoc/logs``; other OS:
  ``~/.local/state/switchloc``; last resort: the current directory.
* ``setup_logging()`` is idempotent; every module uses
  ``logging.getLogger("switchloc.<area>")``.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import traceback
from pathlib import Path

LOG_FILE_NAME = "switchloc.log"
_STATE: dict = {"path": None}


def _candidate_dirs() -> list[Path]:
    out: list[Path] = []
    env = os.environ.get("SWITCHLOC_LOG_DIR")
    if env:
        out.append(Path(env))
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            out.append(Path(base) / "SwitchLoc" / "logs")
    else:
        out.append(Path.home() / ".local" / "state" / "switchloc")
    out.append(Path.cwd() / "logs")
    return out


def setup_logging(level: int = logging.INFO) -> Path | None:
    """Attach the rotating file handler once; return the log path."""
    if _STATE["path"] is not None:
        return _STATE["path"]
    root = logging.getLogger("switchloc")
    root.setLevel(level)
    for d in _candidate_dirs():
        try:
            d.mkdir(parents=True, exist_ok=True)
            path = d / LOG_FILE_NAME
            handler = logging.handlers.RotatingFileHandler(
                path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        except OSError:
            continue
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
        root.addHandler(handler)
        _STATE["path"] = path
        break
    if not root.handlers:                     # no writable folder at all
        root.addHandler(logging.NullHandler())
    return _STATE["path"]


def log_path() -> Path | None:
    """Path of the active log file (``None`` if none is writable)."""
    return _STATE["path"] or setup_logging()


def log_path_text() -> str:
    p = log_path()
    return str(p) if p else "(no writable log folder)"


def get_logger(area: str = "app") -> logging.Logger:
    setup_logging()
    return logging.getLogger(f"switchloc.{area}")


def format_exc(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc,
                                              exc.__traceback__))


def log_exception(exc: BaseException, area: str = "app",
                  context: str = "") -> None:
    """Log an exception with traceback (never raises)."""
    try:
        get_logger(area).error("%s\n%s", context or type(exc).__name__,
                               format_exc(exc))
    except Exception:                          # noqa: BLE001 — logger must not fail
        pass
