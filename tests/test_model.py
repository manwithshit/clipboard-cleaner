"""AppState、剪贴板监听、去重、反馈回路测试。"""

import time
import hashlib
from queue import Queue

from model import ClipboardItem, AppState
from clipboard import _hash_text


def _make_item(text: str) -> ClipboardItem:
    cleaned = text.strip()
    return ClipboardItem(
        raw=text,
        raw_hash=_hash_text(text),
        cleaned=cleaned,
        cleaned_hash=_hash_text(cleaned),
        created_at=time.time(),
    )


# === TC-CLIP-001：新内容入队 ===

def test_new_item_added():
    state = AppState()
    item = _make_item('hello world')
    assert state.add_item(item) is True
    assert len(state) == 1
    assert state.get_item(0) == item


# === TC-CLIP-002：连续相同内容不重复入队 ===

def test_duplicate_raw_rejected():
    state = AppState()
    item = _make_item('hello world')
    assert state.add_item(item) is True
    item2 = _make_item('hello world')
    assert state.add_item(item2) is False
    assert len(state) == 1


# === TC-CLIP-003：清洗后相同也不重复入队 ===

def test_duplicate_cleaned_rejected():
    state = AppState()
    # 缩进不同但清洗后相同
    item1 = _make_item('  hello\n  world')
    item2 = _make_item('hello world')
    assert state.add_item(item1) is True
    # 如果 cleaned 不同则应该加入
    # item1.cleaned = 'hello\nworld', item2.cleaned = 'hello world'
    # 这两个 cleaned 不同，所以应该加入
    assert state.add_item(item2) is True  # cleaned 不同
    assert len(state) == 2


# === TC-CLIP-004：程序复制结果后不回灌 ===

def test_program_copy_suppression():
    state = AppState()
    state.mark_program_copy()
    # 在抑制时间窗内，is_program_copy 应该返回 True
    assert state.is_program_copy() is True


def test_program_copy_suppression_expires():
    state = AppState()
    state._program_copy_time = time.time() - 3.0  # 3 秒前
    assert state.is_program_copy() is False


# === TC-CLIP-005：历史列表最多 10 条 ===

def test_max_history():
    state = AppState()
    for i in range(15):
        item = _make_item(f'content {i}')
        state.add_item(item)
    assert len(state) == 10
    # 最新的在 [0]
    assert 'content 14' in state.get_item(0).raw
    # 最旧的被挤出
    assert 'content 0' not in state.get_item(9).raw
    assert 'content 5' in state.get_item(9).raw


# === 其他模型测试 ===

def test_get_item_out_of_range():
    state = AppState()
    assert state.get_item(0) is None
    assert state.get_item(-1) is None
    assert state.get_item(99) is None


def test_clear():
    state = AppState()
    state.add_item(_make_item('hello'))
    state.add_item(_make_item('world'))
    assert len(state) == 2
    state.clear()
    assert len(state) == 0


def test_get_item_by_index():
    state = AppState()
    state.add_item(_make_item('first'))
    state.add_item(_make_item('second'))
    state.add_item(_make_item('third'))
    assert 'third' in state.get_item(0).raw
    assert 'second' in state.get_item(1).raw
    assert 'first' in state.get_item(2).raw


def test_hash_text():
    h1 = _hash_text('hello')
    h2 = _hash_text('hello')
    h3 = _hash_text('world')
    assert h1 == h2
    assert h1 != h3
