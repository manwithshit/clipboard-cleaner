"""curses TUI 渲染、键盘事件处理、窗口自适应。

面板随 Ghostty pane 宽度/高度自动拉伸，内容多行时自动折行。
"""

from ..state import ClipboardItem, MAX_HISTORY


def _cell_width(text: str) -> int:
    """计算文本的终端显示宽度（考虑 CJK 字符）。"""
    try:
        from wcwidth import wcswidth
        w = wcswidth(text)
        if w >= 0:
            return w
    except ImportError:
        pass
    # 回退：CJK 字符算 2 宽，其他算 1 宽
    width = 0
    for c in text:
        if '一' <= c <= '鿿' or '　' <= c <= '〿' or '＀' <= c <= '￯':
            width += 2
        else:
            width += 1
    return width


def _wrap_line(line: str, width: int) -> list[str]:
    """按终端宽度折行文本，考虑 CJK 字符宽度。"""
    if not line or width <= 0:
        return ['']

    result = []
    current = ''
    current_width = 0

    for char in line:
        char_w = _cell_width(char)
        if current_width + char_w > width and current:
            result.append(current)
            current = char
            current_width = char_w
        else:
            current += char
            current_width += char_w

    if current:
        result.append(current)

    return result


def _truncate_line(line: str, max_width: int) -> str:
    """截断单行到指定终端宽度。"""
    if _cell_width(line) <= max_width:
        return line

    result = ''
    result_width = 0
    for char in line:
        char_w = _cell_width(char)
        if result_width + char_w > max_width:
            break
        result += char
        result_width += char_w

    return result


def _build_display_rows(
    items: list[ClipboardItem],
    width: int,
) -> list[tuple[str, str]]:
    """构建可滚动的历史展示行，返回 (前缀, 文本) 列表。"""
    rows: list[tuple[str, str]] = []
    available_width = max(1, width - 4)  # 预留 "[N] " 前缀

    for i, item in enumerate(items[:MAX_HISTORY]):
        lines = item.cleaned.split('\n')
        wrapped: list[str] = []
        for line in lines:
            wrapped.extend(_wrap_line(line, available_width))

        for j, line in enumerate(wrapped):
            rows.append((f'[{i}] ' if j == 0 else '    ', line))

        if i < min(len(items), MAX_HISTORY) - 1:
            rows.append(('', ''))

    return rows


def _clamp_scroll(offset: int, total_rows: int, visible_rows: int) -> int:
    """把滚动偏移限制在可显示范围内。"""
    max_offset = max(0, total_rows - max(0, visible_rows))
    return min(max(0, offset), max_offset)
