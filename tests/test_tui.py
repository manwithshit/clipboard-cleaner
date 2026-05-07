"""TUI 渲染辅助逻辑测试。"""

import time

from clipboard_cleaner.clipboard import _hash_text
from clipboard_cleaner.state import AppState, ClipboardItem
from clipboard_cleaner.tui import _build_display_rows, _clamp_scroll
from clipboard_cleaner.tui import app as tui_app


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


def test_tui_app_imports_history_limit_for_status_bar():
    """The curses renderer uses MAX_HISTORY when building the status bar."""
    assert tui_app.MAX_HISTORY == 10


class FakeScreen:
    def __init__(self, height: int = 10, width: int = 40):
        self.height = height
        self.width = width
        self.calls: list[tuple] = []

    def erase(self):
        self.calls.append(('erase',))

    def getmaxyx(self):
        return self.height, self.width

    def addnstr(self, *args):
        self.calls.append(('addnstr', args))

    def refresh(self):
        self.calls.append(('refresh',))


def test_tui_render_with_history_item_does_not_crash():
    state = AppState()
    state.add_item(_item('hello world'))
    tui = tui_app.TUI(state, input_queue=None)
    screen = FakeScreen()

    tui._render(screen)

    rendered_text = ''.join(
        call[1][2] for call in screen.calls
        if call[0] == 'addnstr' and len(call[1]) >= 3
    )
    assert 'hello world' in rendered_text
    assert any(call[0] == 'refresh' for call in screen.calls)
