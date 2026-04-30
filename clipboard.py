"""剪贴板轮询、程序复制抑制、重复检测。

后台线程持续轮询系统剪贴板，检测到新内容后经过清洗管线，
通过 queue.Queue 推送给主线程。
"""

from __future__ import annotations

import time
import hashlib
import threading
from queue import Queue, Empty

import pyperclip

from model import ClipboardItem, AppState
from cleaner import clean, has_format_artifacts


def _hash_text(text: str) -> str:
    return hashlib.md5(text.encode('utf-8'), usedforsecurity=False).hexdigest()


class ClipboardMonitor:
    """后台剪贴板监听器。"""

    def __init__(
        self,
        state: AppState,
        output_queue: Queue,
        poll_interval: float = 0.2,
    ):
        self.state = state
        self.output_queue = output_queue
        self.poll_interval = poll_interval
        self._last_content: str = ''
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self):
        """启动后台监听线程。"""
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止监听。"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _poll_loop(self):
        """轮询主循环。"""
        # 初始化：读取当前剪贴板内容作为基线
        try:
            self._last_content = pyperclip.paste()
        except Exception:
            self._last_content = ''

        while self._running:
            try:
                time.sleep(self.poll_interval)
                current = pyperclip.paste()
            except Exception:
                continue

            if not current or current == self._last_content:
                continue

            self._last_content = current

            # 反馈回路抑制：程序刚写入的剪贴板，跳过
            if self.state.is_program_copy():
                continue

            # 幽灵捕获过滤：没有 Claude Code 格式痕迹的内容不加入列表
            # 这样可以过滤掉语音输入、Cmd+A 全选、其他应用复制的干净文本
            if not has_format_artifacts(current):
                continue

            # 去重检查
            raw_hash = _hash_text(current)
            cleaned = clean(current)
            cleaned_hash = _hash_text(cleaned)

            if not cleaned:
                continue  # 清洗后为空，跳过

            item = ClipboardItem(
                raw=current,
                cleaned=cleaned,
                raw_hash=raw_hash,
                cleaned_hash=cleaned_hash,
                created_at=time.time(),
            )

            if self.state.add_item(item):
                try:
                    self.output_queue.put_nowait(item)
                except Exception:
                    pass  # 队列满，丢弃
