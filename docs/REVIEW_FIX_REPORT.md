# 剪贴板清洗面板审阅修复报告

日期：2026-04-30

## 修复范围

本次针对代码审阅中的 5 个发现做了实现修复，并补充回归测试：

1. 带行首装饰的 fenced code block 被误判为普通段落。
2. 去重 hash 历史使用 `set -> list` 修剪，顺序不可靠。
3. TUI 渲染时未加锁直接读取共享 `history`。
4. 程序写入剪贴板后才标记抑制，存在极小竞态窗口。
5. 嵌套引用层级被丢弃，导致多行嵌套引用被硬换行合并。

## 关键改造

### cleaner.py

- 将清洗流程调整为先剥离终端/Claude 行首装饰，再做 block 分类。
- 新增 `quote` block 类型。嵌套引用行不再进入普通段落硬换行合并流程。
- 补充识别首行无缩进、后续硬换行行带 2 空格缩进的 Claude/Ghostty continuation pattern，避免真实复制内容被幽灵过滤误杀。
- 清洗普通段落时会移除 continuation 行的 2 空格缩进，并在 CJK/中文标点边界直接拼接；英文单词接中文仍保留空格。
- Markdown pipe 表格会转成数字条目列表，保留每行含义但不保留表格结构，便于粘贴到微信等聊天窗口。
- 新增 `_strip_code_decorations()`，用于处理从带装饰区域复制出的代码块：
  - 去掉外层 `|`、`>`、`▎` 等装饰符。
  - 保留代码块内部真实缩进。
- 对带装饰的 fenced code block 持续剥离代码块内部装饰，直到 closing fence。

### model.py

- 用 `deque + set` 替代无序 `set` 修剪，确保 hash 去重窗口按插入顺序淘汰。
- 新增 `snapshot()`，TUI 可以在锁内拿到历史快照。
- `mark_program_copy()` / `is_program_copy()` 支持传入具体文本，通过 hash 做精确抑制。

### clipboard.py

- 剪贴板轮询时调用 `state.is_program_copy(current)`，只抑制程序刚写入的精确内容。

### tui.py

- 复制前先调用 `state.mark_program_copy(item.cleaned)`，缩小反馈回路竞态窗口。
- 渲染历史列表时改用 `state.snapshot()`，避免跨线程无锁读共享 deque。
- 新增历史内容滚动浏览：支持 `↑/↓`、`j/k`、`PageUp/PageDown`、`Home/End`，长内容或 10 条历史超过屏幕高度时不再被截断。

### docs/TECHNICAL_DESIGN.md

- 将 Ghostty 鼠标选中 / Command+A 全选终端内容纳入正式捕获能力说明。
- 更新 TUI 交互说明，补充滚动按键和“新内容回到顶部”的行为。

## 新增测试

新增 5 个回归测试：

- `test_decorated_code_block_not_merged`
- `test_nested_quote_lines_preserve_breaks`
- `test_snapshot_returns_newest_first_copy`
- `test_duplicate_rejected_after_hash_history_prune`
- `test_program_copy_can_suppress_exact_content`
- `test_detect_claude_continuation_indent_artifact`
- `test_remove_claude_continuation_indent`
- `test_table_converted_to_narrative_items`
- `test_table_with_uneven_cells_converted_to_narrative_items`
- `tests/test_tui.py::test_build_display_rows_keeps_all_history_lines`
- `tests/test_tui.py::test_clamp_scroll_limits_offset_to_available_rows`

这些测试在修复前会失败，修复后通过。

## 验证结果

已执行以下命令：

```bash
python3 -m pytest tests/test_cleaner.py::test_decorated_code_block_not_merged tests/test_cleaner.py::test_nested_quote_lines_preserve_breaks tests/test_model.py::test_duplicate_rejected_after_hash_history_prune tests/test_model.py::test_snapshot_returns_newest_first_copy tests/test_model.py::test_program_copy_can_suppress_exact_content -q
```

结果：

```text
5 passed in 0.01s
```

```bash
python3 -m pytest -q
```

结果：

```text
60 passed in 0.04s
```

```bash
python3 -m py_compile run.py model.py clipboard.py cleaner.py tui.py
```

结果：退出码 0，无语法错误输出。

## 后续建议

## Obsidian Callout 清洗（2026-04-30 追加）

用户反馈 Obsidian callout 语法（`[!tip]`、`[!note]` 等）在终端中不可见，需要在清洗时去除。

### 改动

- `cleaner.py`：新增 `_OBSIDIAN_CALLOUT` 正则，在 `_strip_decorations()` 中去掉引用装饰后的裸 callout 标记。
- 新增 3 个测试：`test_obsidian_callout_stripped`、`test_obsidian_callout_with_quote_decor`、`test_obsidian_various_callouts`。
- 更新 `TECHNICAL_DESIGN.md` 问题背景和 v2→v3 变更记录。

- `has_format_artifacts()` 仍建议从“任一命中”升级为评分模型，降低干净 Markdown / 缩进笔记的误捕获。
- curses resize 仍可进一步补 `KEY_RESIZE` / `curses.update_lines_cols()` 的显式处理。
- 普通段落硬换行合并仍可结合终端宽度或行长分布做更保守判断。
