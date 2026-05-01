"""TUI 渲染辅助逻辑测试。"""

import time

from clipboard import _hash_text
from model import ClipboardItem
from tui import _build_display_rows, _clamp_scroll


def _item(text: str) -> ClipboardItem:
    return ClipboardItem(
        raw=text,
        cleaned=text,
        raw_hash=_hash_text(text),
        cleaned_hash=_hash_text(text),
        created_at=time.time(),
    )


def test_build_display_rows_keeps_all_history_lines():
    items = [_item(f'item {i}\nline {i}') for i in range(3)]

    rows = _build_display_rows(items, width=40)

    rendered = [prefix + text for prefix, text in rows]
    assert '[0] item 0' in rendered
    assert '    line 0' in rendered
    assert '[2] item 2' in rendered
    assert '    line 2' in rendered


def test_clamp_scroll_limits_offset_to_available_rows():
    assert _clamp_scroll(-1, total_rows=10, visible_rows=4) == 0
    assert _clamp_scroll(3, total_rows=10, visible_rows=4) == 3
    assert _clamp_scroll(99, total_rows=10, visible_rows=4) == 6
    assert _clamp_scroll(5, total_rows=3, visible_rows=4) == 0
