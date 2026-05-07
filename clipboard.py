"""Backward-compatible imports for clipboard monitoring.

New code should import from `clipboard_cleaner.clipboard`.
"""

from clipboard_cleaner.clipboard.monitor import ClipboardMonitor, _hash_text

__all__ = ["ClipboardMonitor", "_hash_text"]
