"""curses TUI 渲染、键盘事件处理、窗口自适应。

面板随 Ghostty pane 宽度/高度自动拉伸，内容多行时自动折行。
"""

import curses
import textwrap
from queue import Queue, Empty

import pyperclip

from model import ClipboardItem, AppState, MAX_HISTORY


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


class TUI:
    """终端用户界面。"""

    def __init__(self, state: AppState, input_queue: Queue):
        self.state = state
        self.input_queue = input_queue  # 从 clipboard monitor 来的新条目
        self.status_message: str = '监听中...'
        self.status_time: float = 0

    def run(self):
        """主循环。使用 curses.wrapper 保证退出时恢复终端。"""
        curses.wrapper(self._main)

    def _main(self, stdscr):
        curses.curs_set(0)  # 隐藏光标
        stdscr.nodelay(True)  # 非阻塞键盘
        stdscr.timeout(200)  # getch 超时 200ms

        # 尝试启用 256 色
        if curses.has_colors():
            curses.start_color()
            try:
                curses.use_default_colors()
            except curses.error:
                pass
            curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_GREEN)  # 标题栏
            curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # 状态栏
            curses.init_pair(3, curses.COLOR_CYAN, curses.COLOR_BLACK)   # 序号
            curses.init_pair(4, curses.COLOR_RED, curses.COLOR_BLACK)    # 提示
        else:
            for i in range(1, 5):
                curses.init_pair(i, 0, 0)

        self._render(stdscr)

        while True:
            key = stdscr.getch()

            if key == -1:
                # 无键盘输入，检查是否有新条目
                self._check_new_items()
                self._render(stdscr)
                continue

            # 按键处理
            if key == ord('q') or key == ord('Q'):
                break
            elif key == ord('c') or key == ord('C'):
                self.state.clear()
                self._set_status('已清空')
            elif ord('0') <= key <= ord('9'):
                index = key - ord('0')
                item = self.state.get_item(index)
                if item:
                    try:
                        pyperclip.copy(item.cleaned)
                        self.state.mark_program_copy()
                        self._set_status(f'已复制 [{index}]')
                    except Exception as e:
                        self._set_status(f'复制失败: {e}')
                else:
                    self._set_status(f'没有 [{index}] 条目')

            self._render(stdscr)

    def _check_new_items(self):
        """从队列中取出新条目（不阻塞）。"""
        try:
            while True:
                item = self.input_queue.get_nowait()
                self._set_status('新内容已捕获')
        except Empty:
            pass

    def _set_status(self, msg: str):
        self.status_message = msg
        self.status_time = __import__('time').time()

    def _render(self, stdscr):
        """渲染整个界面。"""
        import time
        stdscr.erase()
        height, width = stdscr.getmaxyx()

        if height < 5 or width < 20:
            stdscr.addnstr(0, 0, '窗口太小，至少 20x5', width - 1)
            stdscr.refresh()
            return

        # 标题栏
        title = ' Clipboard Cleaner '
        try:
            stdscr.addnstr(0, 0, title.ljust(width), width - 1, curses.color_pair(1) | curses.A_BOLD)
        except curses.error:
            pass

        # 内容区域
        content_top = 1
        content_bottom = height - 2  # 留一行状态栏

        # 获取所有条目
        items = list(self.state.history)
        if not items:
            try:
                stdscr.addnstr(content_top, 0, '  等待剪贴板内容...' + ' ' * (width - 20), width - 1)
            except curses.error:
                pass
        else:
            # 计算每条需要多少行
            item_lines = []  # [(index, [lines])]
            available_width = width - 4  # 预留 "[N] " 前缀

            for i, item in enumerate(items):
                if i >= MAX_HISTORY:
                    break
                lines = item.cleaned.split('\n')
                wrapped = []
                for line in lines:
                    wrapped.extend(_wrap_line(line, available_width))
                # 限制每条最多显示的内容行数
                max_content_lines = content_bottom - content_top - 1
                if sum(len(w) for w in wrapped) > max_content_lines:
                    # 截断
                    total = 0
                    truncated = []
                    for wl in wrapped:
                        total += 1
                        truncated.append(wl)
                        if total >= max_content_lines:
                            break
                    wrapped = truncated

                item_lines.append((i, wrapped))

            # 渲染条目
            y = content_top
            for idx, lines in item_lines:
                if y >= content_bottom:
                    break

                # 序号
                prefix = f'[{idx}] '
                try:
                    stdscr.addnstr(y, 0, prefix, width - 1, curses.color_pair(3))
                except curses.error:
                    pass

                # 内容行
                for j, line in enumerate(lines):
                    if y >= content_bottom:
                        break
                    if j == 0:
                        # 第一行已经在序号后面了
                        try:
                            x = _cell_width(prefix)
                            remaining = width - x - 1
                            display = _truncate_line(line, remaining)
                            if x < width:
                                stdscr.addnstr(y, x, display, width - x - 1)
                        except curses.error:
                            pass
                    else:
                        try:
                            display = _truncate_line(line, width - 1)
                            stdscr.addnstr(y, 0, ' ' * 4 + display, width - 1)
                        except curses.error:
                            pass
                    y += 1

                # 条目间空一行（如果有空间）
                if y < content_bottom - 1:
                    y += 1

        # 状态栏
        import time
        status_y = height - 1
        try:
            count = len(self.state)
            # 状态消息 3 秒后淡出
            if time.time() - self.status_time > 3:
                self.status_message = '监听中...'
            status = f' {self.status_message}  {count}/{MAX_HISTORY}  | 0-9:复制 C:清空 q:退出 '
            # 填充到宽度
            padded = status.ljust(width)
            stdscr.addnstr(status_y, 0, padded[:width-1], width - 1, curses.color_pair(2))
        except curses.error:
            pass

        stdscr.refresh()
