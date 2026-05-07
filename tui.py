"""Backward-compatible imports for the terminal UI.

New code should import from `clipboard_cleaner.tui`.
"""

from clipboard_cleaner.tui import (
    TUI,
    _build_display_rows,
    _cell_width,
    _clamp_scroll,
    _truncate_line,
    _wrap_line,
)

__all__ = [
    "TUI",
    "_build_display_rows",
    "_cell_width",
    "_clamp_scroll",
    "_truncate_line",
    "_wrap_line",
]
