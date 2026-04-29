"""Clipboard Cleaner 入口。

用法:
    python run.py          # 启动 TUI 模式
    python run.py --plain  # 纯文本模式（无 curses）
"""

import argparse
import sys
import signal
from queue import Queue

from model import AppState, QUEUE_MAX_SIZE
from clipboard import ClipboardMonitor
from cleaner import clean


def run_tui():
    """TUI 模式。"""
    from tui import TUI

    state = AppState()
    item_queue: Queue = Queue(maxsize=QUEUE_MAX_SIZE)

    monitor = ClipboardMonitor(state, item_queue)
    monitor.start()

    tui = TUI(state, item_queue)

    def handle_signal(signum, frame):
        monitor.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        tui.run()
    finally:
        monitor.stop()


def run_plain():
    """纯文本模式：读取 stdin，输出清洗结果。"""
    raw = sys.stdin.read()
    if not raw.strip():
        print('(空)', file=sys.stderr)
        return
    cleaned = clean(raw)
    if not cleaned:
        print('(清洗后为空)', file=sys.stderr)
    else:
        print(cleaned)


def main():
    parser = argparse.ArgumentParser(description='Clipboard Cleaner — 剪贴板清洗面板')
    parser.add_argument('--plain', action='store_true', help='纯文本模式（从 stdin 读取）')
    args = parser.parse_args()

    if args.plain:
        run_plain()
    else:
        run_tui()


if __name__ == '__main__':
    main()
