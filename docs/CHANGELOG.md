# 改造档案

记录历次重要逻辑改造，方便后续追溯设计决策。

---

## 2026-05-04｜提升触发灵敏度 + 简化去重逻辑

### 背景

实际使用中发现两类内容应该被捕获却被漏掉：

1. **box-drawing 表格**（`┌─┐` `│` `└─┘` 等字符组成的表格）从终端复制过来，没能进入历史列表。
2. **多行中文段落**（典型的 Claude Code 中文输出）即使按 C 清空后重新复制，也常常进不来。

定位发现两个根因：

**根因 1：`has_format_artifacts()` 检测条件不全**
- 引用装饰的字符集里漏了 `│` (U+2502)，这正是表格用的边框字符
- 边框检测要求**整行**全是 box-drawing 字符，混合内容（如 `│ 武将 │`）不触发
- 没检测 Claude Code 自己的输出标记 `⏺` `⎿`
- 中文长段落场景没有兜底规则

**根因 2：`AppState` 的 50 条 hash 缓存超出预期边界**
- 历史只保留 10 条，但去重 hash 缓存了 50 条
- 用户按 C 清空历史后，hash 缓存仍在，导致再次复制相同内容被跳过
- 即便没清空，被挤出 10 条历史的旧条目仍参与去重，违反直觉

### 改动内容

**`cleaner.py` — `has_format_artifacts()` 重构**

| # | 检测条件 | 状态 |
|---|---------|------|
| 1 | 公共缩进 ≥ 2 空格 | 保留 |
| 2 | 首行无缩进 + 后续行缩进 ≥ 2 空格 | 保留 |
| 3 | 行首引用装饰 | **修 bug**：补充 `│` (U+2502) |
| 4 | box-drawing 字符检测 | **放宽**：从「整行边框」改为「行内含 ≥ 3 连续 box-drawing 字符」 |
| 5 | Claude Code 标记 `⏺` `⎿` | **新增** |
| 6 | Trailing spaces / Tab | 保留 |
| 7 | 代码块围栏 | 保留 |
| 8 | ≥ 3 行的中文文本 | **新增**（兜底） |

新增正则常量：
- `_BOX_DRAWING_RUN`：匹配行内 ≥ 3 个连续 box-drawing 字符
- `_HAS_CJK`：匹配中文字符（CJK Unified Ideographs）

**`model.py` — `AppState` 去重逻辑简化**

- 删除 `_recent_raw_hashes` / `_recent_cleaned_hashes` / `_recent_raw_order` / `_recent_cleaned_order` / `_MAX_HASH_HISTORY` 这些字段
- 删除 `_remember_hash()` 方法
- `add_item()` 改为直接遍历当前 `history` deque（最多 10 条）做去重比对
- 去重边界 = 当前历史，被挤出的旧条目可重新加入；按 C 清空后所有内容都可重新加入

### 测试

- 修改 `tests/test_model.py`：
  - 删除 `test_duplicate_rejected_after_hash_history_prune`（依赖已删除字段）
  - 新增 `test_dedup_bounded_by_history_only`：验证被挤出历史的条目可重新加入
  - 新增 `test_dedup_after_clear`：验证 clear 后相同内容可重新加入
- 新增 `tests/test_cleaner.py` 用例：
  - `test_detect_box_drawing_table`：完整 box-drawing 表格触发
  - `test_detect_box_drawing_run_inline`：正文中含连续 ─── 触发
  - `test_detect_claude_code_markers`：⏺ ⎿ 触发
  - `test_detect_chinese_multiline_fallback`：多行中文兜底触发
  - `test_skip_short_clean_text`：单行纯英文不触发（避免误捕获语音输入）

**测试结果：124 / 124 通过**

### 影响

- 灵敏度提升，但仍保留对纯文本（语音输入、Cmd+A 等）的过滤
- 去重逻辑更直觉：用户按 C 清空 = 完全重置；没清空时只看当前 10 条
