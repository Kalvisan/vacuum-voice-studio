"""Restore terminal state after TUI apps exit or crash."""

from __future__ import annotations

import subprocess
import sys


def restore_terminal() -> None:
    """Return stdin/stdout to a usable shell state after Textual or curses."""
    if not sys.stdin.isatty() and not sys.stdout.isatty():
        return

    try:
        subprocess.run(["stty", "sane"], check=False, stderr=subprocess.DEVNULL)
    except OSError:
        pass

    if sys.stdout.isatty():
        for sequence in (
            "\033[?1049l",
            "\033[?25h",
            "\033[0m",
            "\033[?1000l",
            "\033[?1002l",
            "\033[?1003l",
        ):
            sys.stdout.write(sequence)
        sys.stdout.flush()
