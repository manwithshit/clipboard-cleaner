"""Backward-compatible imports for the cleaning pipeline.

New code should import from `clipboard_cleaner.cleaner`.
"""

from clipboard_cleaner.cleaner.pipeline import clean, has_format_artifacts

__all__ = ["clean", "has_format_artifacts"]
