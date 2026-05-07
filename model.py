"""Backward-compatible imports for application state.

New code should import from `clipboard_cleaner.state`.
"""

from clipboard_cleaner.state import (
    CLIPBOARD_POLL_INTERVAL,
    MAX_HISTORY,
    PROGRAM_COPY_SUPPRESS_SECONDS,
    QUEUE_MAX_SIZE,
    AppState,
    ClipboardItem,
)

__all__ = [
    "AppState",
    "ClipboardItem",
    "MAX_HISTORY",
    "CLIPBOARD_POLL_INTERVAL",
    "PROGRAM_COPY_SUPPRESS_SECONDS",
    "QUEUE_MAX_SIZE",
]
