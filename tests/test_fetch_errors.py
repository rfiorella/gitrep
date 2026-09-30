"""Characterization tests for fetch error paths (TEST_CHANGE_PROPOSALS T1)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from gitrep import fetch as fetch_mod
from gitrep.fetch import fetch_all


def _raise(exc: BaseException):
    def _run(*_a, **_kw):
        raise exc

    return _run


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (subprocess.TimeoutExpired(["git"], 99), "timeout after 3.0s"),
        (PermissionError("x"), "PermissionError: x"),
        (OSError("boom"), "OSError: boom"),
    ],
)
def test_fetch_exception_messages(monkeypatch, exc, expected):
    monkeypatch.setattr(fetch_mod.subprocess, "run", _raise(exc))
    res = fetch_all([Path("/r")], timeout=3.0)
    fr = res[Path("/r")]
    assert fr.ok is False
    assert fr.stderr == expected
    assert fr.duration_s >= 0


def test_fetch_git_not_found(monkeypatch):
    monkeypatch.setattr(fetch_mod.subprocess, "run", _raise(FileNotFoundError("git")))
    fr = fetch_all([Path("/r")])[Path("/r")]
    assert fr.ok is False
    assert fr.stderr == "git not found: git"
    assert fr.duration_s >= 0


def test_fetch_unicode_decode_error(monkeypatch):
    exc = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
    monkeypatch.setattr(fetch_mod.subprocess, "run", _raise(exc))
    fr = fetch_all([Path("/r")])[Path("/r")]
    assert fr.ok is False
    assert fr.stderr.startswith("UnicodeDecodeError: ")


def test_fetch_nonzero_returncode_strips_stderr(monkeypatch):
    def fake_run(cmd, *_a, **_kw):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="  boom\n")

    monkeypatch.setattr(fetch_mod.subprocess, "run", fake_run)
    fr = fetch_all([Path("/r")])[Path("/r")]
    assert fr.ok is False
    assert fr.stderr == "boom"


def test_fetch_command_line(monkeypatch):
    seen = {}

    def fake_run(cmd, *_a, **kw):
        seen["cmd"] = cmd
        seen["timeout"] = kw.get("timeout")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(fetch_mod.subprocess, "run", fake_run)
    fr = fetch_all([Path("/r")], timeout=7.0)[Path("/r")]
    assert fr.ok is True
    assert fr.stderr == ""
    assert seen["cmd"] == ["git", "-C", "/r", "fetch", "--all", "--prune", "--quiet"]
    assert seen["timeout"] == 7.0
