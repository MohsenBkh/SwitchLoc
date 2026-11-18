#!/usr/bin/env python3
"""Run a build command, echo combined output, and append it to a UTF-8 log."""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


_NTSTATUS_HINTS = {
    0xC000013A: "STATUS_CONTROL_C_EXIT — the process was interrupted (Ctrl+C or the console window was closed), not a normal exit",
    0xC0000005: "STATUS_ACCESS_VIOLATION — the process crashed (invalid memory access)",
    0xC0000409: "STATUS_STACK_BUFFER_OVERRUN — the process crashed (stack buffer overrun)",
    0xC00000FD: "STATUS_STACK_OVERFLOW — the process ran out of stack",
    0xC0000374: "STATUS_HEAP_CORRUPTION — the process crashed (heap corruption)",
}


def _describe_exit_code(code: int) -> str:
    """Return a human-readable hint for well-known Windows NTSTATUS exit codes."""
    unsigned = code if code >= 0 else code + 0x100000000
    return _NTSTATUS_HINTS.get(unsigned, "")


def _write_console(data: bytes) -> None:
    """Pass child bytes through unchanged so Windows console output is preserved."""
    stream = getattr(sys.stdout, "buffer", None)
    if stream is not None:
        stream.write(data)
        stream.flush()
    else:  # pragma: no cover - fallback for unusual embedded interpreters
        sys.stdout.write(data.decode("utf-8", errors="replace"))
        sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 3 or args[1] != "--":
        print("Usage: run_logged.py LOG_FILE -- COMMAND [ARG ...]", file=sys.stderr)
        return 2

    log_path = Path(args[0])
    command = args[2:]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")

    try:
        with log_path.open("a", encoding="utf-8", errors="replace") as log:
            log.write(f"\n[{stamp}] COMMAND: {subprocess.list2cmdline(command)}\n")
            log.flush()
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                env=env, bufsize=0)
            assert process.stdout is not None
            while True:
                chunk = os.read(process.stdout.fileno(), 4096)
                if not chunk:
                    break
                log.write(chunk.decode("utf-8", errors="replace"))
                log.flush()
                _write_console(chunk)
            code = process.wait()
            hint = _describe_exit_code(code)
            log.write(f"\n[{datetime.now().astimezone().isoformat(timespec='seconds')}] "
                      f"EXIT CODE: {code}\n")
            if hint:
                log.write(f"EXIT CODE MEANING: {hint}\n")
                print(f"\n[run_logged] {hint}\n")
            log.flush()
            return code
    except OSError as exc:
        with log_path.open("a", encoding="utf-8", errors="replace") as log:
            log.write(f"[{stamp}] FAILED TO START COMMAND: {exc}\n")
        print(f"Could not start build command: {exc}", file=sys.stderr)
        return 127


if __name__ == "__main__":
    raise SystemExit(main())
