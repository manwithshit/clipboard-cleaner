"""Backward-compatible script entry point.

Prefer `python3 -m clipboard_cleaner.cli` for package-style execution.
"""

from clipboard_cleaner.cli import main, run_plain, run_tui

__all__ = ["main", "run_plain", "run_tui"]


if __name__ == "__main__":
    main()
