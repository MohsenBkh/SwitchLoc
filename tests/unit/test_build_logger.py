from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


LOGGER = Path(__file__).resolve().parents[2] / "build_tools" / "run_logged.py"
UTF8_ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def test_build_logger_streams_and_records_stdout_and_stderr(tmp_path):
    log = tmp_path / "build_error.log"
    child = (
        "import sys; print('build output فارسی'); "
        "print('diagnostic detail', file=sys.stderr)"
    )
    result = subprocess.run(
        [sys.executable, str(LOGGER), str(log), "--", sys.executable, "-c", child],
        capture_output=True, check=False, env=UTF8_ENV)

    assert result.returncode == 0
    assert "build output" in result.stdout.decode(errors="replace")
    contents = log.read_text(encoding="utf-8")
    assert "COMMAND:" in contents
    assert "build output فارسی" in contents
    assert "diagnostic detail" in contents
    assert "EXIT CODE: 0" in contents


def test_build_logger_records_nonzero_exit_code(tmp_path):
    log = tmp_path / "failed-build.log"
    result = subprocess.run(
        [sys.executable, str(LOGGER), str(log), "--", sys.executable,
         "-c", "import sys; print('compile failed'); sys.exit(23)"],
        capture_output=True, check=False)

    assert result.returncode == 23
    contents = log.read_text(encoding="utf-8")
    assert "compile failed" in contents
    assert "EXIT CODE: 23" in contents


def test_build_logger_explains_windows_ntstatus_exit_code(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("run_logged", LOGGER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module._describe_exit_code(3221225786) == module._NTSTATUS_HINTS[0xC000013A]
    assert module._describe_exit_code(0xC000013A) == module._NTSTATUS_HINTS[0xC000013A]
    assert module._describe_exit_code(1) == ""
