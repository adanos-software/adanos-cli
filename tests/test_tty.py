"""TTY/output helper tests for the adanos CLI."""

from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path


from adanos_cli.tty import is_interactive, should_output_json, supports_color


def test_should_output_json_explicit_json_flag() -> None:
    assert should_output_json(Namespace(output="json", json=False, quiet=False), argv_supplied=True) is True


def test_should_output_json_quiet_implies_json() -> None:
    assert should_output_json(Namespace(output="text", json=False, quiet=True), argv_supplied=True) is True


def test_should_output_json_auto_for_real_cli_when_stdout_not_tty(monkeypatch) -> None:
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    assert should_output_json(Namespace(output=None, json=False, quiet=False), argv_supplied=False) is True


def test_should_output_json_explicit_text_beats_pipe_auto_json(monkeypatch) -> None:
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    assert should_output_json(Namespace(output="text", json=False, quiet=False), argv_supplied=False) is False


def test_should_output_json_plain_beats_pipe_auto_json(monkeypatch) -> None:
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    assert should_output_json(Namespace(output=None, json=False, quiet=False, plain=True), argv_supplied=False) is False


def test_should_output_json_explicit_json_beats_plain(monkeypatch) -> None:
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    assert should_output_json(Namespace(output="json", json=False, quiet=False, plain=True), argv_supplied=False) is True
    assert should_output_json(Namespace(output=None, json=True, quiet=False, plain=True), argv_supplied=False) is True
    assert should_output_json(Namespace(output=None, json=False, quiet=True, plain=True), argv_supplied=False) is True


def test_should_output_json_does_not_auto_switch_for_programmatic_calls(monkeypatch) -> None:
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    assert should_output_json(Namespace(output="text", json=False, quiet=False), argv_supplied=True) is False


def test_is_interactive_true_for_real_tty(monkeypatch) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    assert is_interactive() is True


def test_is_interactive_false_in_ci(monkeypatch) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setenv("CI", "true")
    assert is_interactive() is False


def test_is_interactive_false_for_dumb_term(monkeypatch) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("TERM", "dumb")
    assert is_interactive() is False


def test_supports_color_requires_tty_and_term(monkeypatch) -> None:
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert supports_color() is True


def test_supports_color_false_without_tty(monkeypatch) -> None:
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    monkeypatch.setenv("TERM", "xterm-256color")
    assert supports_color() is False


def test_supports_color_false_without_term(monkeypatch) -> None:
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.delenv("TERM", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert supports_color() is False


def test_supports_color_respects_no_color(monkeypatch) -> None:
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setenv("NO_COLOR", "1")
    assert supports_color() is False
