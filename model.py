"""Clipboard Cleaner — 剪贴板清洗面板

后台监听系统剪贴板，自动清洗 Claude Code / 终端复制文本中的
硬换行、公共缩进、引用竖线等格式噪音，在终端 TUI 中展示
最近 10 条清洗结果。按数字键 0-9 复制指定条目到系统剪贴板。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque
from queue import Queue, Full
import hashlib
import time
import threading
import sys
import curses

# --- Constants ---

MAX_HISTORY = 10  # UI 展示的历史条目上限
CLIPBOARD_POLL_INTERVAL = 0.2  # 剪贴板轮询间隔 (秒)
PROGRAM_COPY_SUPPRESS_SECONDS = 1.5  # 程序写入剪贴板后的抑制时间窗
QUEUE_MAX_SIZE = 20  # 跨线程通信队列缓冲上限

# --- Data Model ---

@dataclass
class ClipboardItem:
    """一条清洗后的剪贴板条目。"""
    raw: str
    cleaned: str
    raw_hash: str
    cleaned_hash: str
    created_at: float  # time.time()


class AppState:
    """线程安全的共享状态。"""

    def __init__(self):
        self.history: deque[ClipboardItem] = deque(maxlen=MAX_HISTORY)
        self.lock = threading.Lock()

        # 去重：最近 N 条 raw_hash + cleaned_hash
        self._recent_raw_hashes: set[str] = set()
        self._recent_cleaned_hashes: set[str] = set()
        self._MAX_HASH_HISTORY = 50

        # 反馈回路抑制
        self._program_copy_time: float = 0  # 最近一次程序写入剪贴板的时间

    def add_item(self, item: ClipboardItem) -> bool:
        """添加新条目。若已存在则返回 False。"""
        with self.lock:
            if item.raw_hash in self._recent_raw_hashes:
                return False
            if item.cleaned_hash in self._recent_cleaned_hashes:
                return False

            self.history.appendleft(item)
            self._recent_raw_hashes.add(item.raw_hash)
            self._recent_cleaned_hashes.add(item.cleaned_hash)

            # 清理过期的 hash 历史（避免无限增长）
            if len(self._recent_raw_hashes) > self._MAX_HASH_HISTORY:
                # 简单策略：保留最新的一半
                recent = list(self._recent_raw_hashes)
                self._recent_raw_hashes = set(recent[-self._MAX_HASH_HISTORY // 2:])
                recent = list(self._recent_cleaned_hashes)
                self._recent_cleaned_hashes = set(recent[-self._MAX_HASH_HISTORY // 2:])

            return True

    def get_item(self, index: int) -> ClipboardItem | None:
        with self.lock:
            if 0 <= index < len(self.history):
                return self.history[index]
            return None

    def clear(self):
        with self.lock:
            self.history.clear()

    def mark_program_copy(self):
        """标记程序写入了剪贴板（启动抑制时间窗）。"""
        self._program_copy_time = time.time()

    def is_program_copy(self) -> bool:
        """检查当前是否处于程序写入的抑制时间窗内。"""
        return (time.time() - self._program_copy_time) < PROGRAM_COPY_SUPPRESS_SECONDS

    def __len__(self):
        with self.lock:
            return len(self.history)
