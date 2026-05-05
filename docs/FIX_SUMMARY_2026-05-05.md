# 修复总结 — 2026-05-05

修复 Codex 在 `docs/ISSUE_INVESTIGATION_2026-05-05.md` 中诊断的两个清洗 bug。

---

## 一、问题回顾

### Bug 1：frontmatter 假阳性导致内容被吞

**症状**：复制如下内容，TUI 面板没有任何反应。

```
---
正文
---
```

**根因**：`_strip_frontmatter()` 只看是否被两个 `---` 包围，不验证中间是否真的是 YAML key-value 结构。结果整段被当成 metadata 剥离，`clean()` 返回空字符串，被 `clipboard.py` 第 86 行 `if not cleaned: continue` 直接丢弃。

### Bug 2：窄终端折行的 box-drawing 表格清洗错乱

**症状**：从压窄的终端复制表格，输出被破坏：

```
〔引〕      人物          │       性格
〔引〕

林黛玉
多愁善感      │
```

**根因**：终端按列宽折行后，单一表格行被切成多个物理行（如 `│ 林黛玉 │ 多愁善感 │` 折成 `│ 林黛玉 │` + `多愁善感 │`）。`_is_box_table_line()` 只识别完整行，碎片落入 `_strip_decorations()`，其中 `│` 被当成引用装饰加上 `〔引〕`，结构在表格解析之前就被破坏。

---

## 二、修复方案

### 修复 1：frontmatter 启发式判断

**新增** [`cleaner.py`](../cleaner.py) `_looks_like_yaml_frontmatter(body_lines) -> bool`：

只在以下都满足时才判定为 YAML frontmatter：
- 至少有一个 `key: value` 行
- 除 key-value、缩进续行（仅在前一行是 key 之后）、注释行（`#`）、空行外，不存在其他类型的内容

如果中间内容看起来不是纯 YAML（例如夹杂普通文本），**只去掉首尾两个 `---` 分隔符**，正文保留。

新增正则常量：`_YAML_KEY_LINE`、`_YAML_CONT_LINE`、`_YAML_COMMENT_LINE`。

### 修复 2：表格折行预处理

**新增** [`cleaner.py`](../cleaner.py) `_merge_wrapped_box_table_lines(lines) -> list[str]`：

在 `clean()` 流程的 Step 2b（在 rstrip 之后、分类之前）加入预处理。规则：

- 当前行以表格 opener（`┌┏├┝└┗│┃`）开头时进入合并流程
- 如果当前未形成完整 `_is_box_table_line()`，**必须**吞并下一非空行
- 如果当前已完整，只在下一行明显是「续行碎片」时才继续吞并：
  - 不能以新行起始字符（`┌├└`）开头
  - 末尾是 closer（`│┃┐┓┤┥┘┛`）或整行仅由 box 字符 + 空白组成

新增常量：`_BOX_TABLE_OPENERS`、`_BOX_TABLE_CLOSERS`、`_NEW_ROW_STARTERS`。

---

## 三、测试

### 新增 fixtures（[`tests/fixtures/`](../tests/fixtures/)）

| 文件 | 场景 |
|------|------|
| `frontmatter_false_positive_*` | `---\n正文\n---` 的非 YAML 包围 |
| `wrapped_box_table_*` | 单单元格表格被折成 6 行 |
| `wrapped_box_table_multicol_*` | 多列多行表格被压窄折行 |

### 新增单元测试（[`tests/test_cleaner.py`](../tests/test_cleaner.py)）

frontmatter 部分（7 个）：
- `test_frontmatter_false_positive_kept_as_content`
- `test_frontmatter_false_positive_with_indent`
- `test_frontmatter_false_positive_chinese_paragraph`
- `test_frontmatter_real_yaml_still_strips`
- `test_frontmatter_yaml_with_list_value`
- `test_frontmatter_yaml_with_comment`
- `test_frontmatter_mixed_content_not_stripped`

表格折行部分（5 个）：
- `test_wrapped_box_table_single_cell`
- `test_wrapped_box_table_multicol`
- `test_wrapped_box_table_orphan_pipe_continuation`
- `test_unwrapped_box_table_still_works`
- `test_no_table_content_unaffected`

### 测试结果

```
139 passed in 0.11s
```

124 个原有测试全部通过，新增 12 个用例 + 3 组 fixture（共 15 个新检查）全部通过。

---

## 四、回归验证（用户原始失败 case）

| Case | 修复前 | 修复后 |
|------|-------|--------|
| `  ---\n  正文\n  ---` | clean() 返回空 → 不进面板 | `'正文'` ✓ |
| 完整表格无 `---` | dedup 命中（已修复） | 正常转条目 ✓ |
| 折行表格 | `〔引〕      人物 │` 错乱 | `1. 人物：林黛玉 / 性格：多愁善感` ✓ |
| `---\n正文\n---` | 返回空 | `'正文'` ✓ |
| 单单元格折行 | 不识别 | `'林黛玉'` ✓ |
| 真 YAML frontmatter（保护性测试） | 正常剥离 | 正常剥离 ✓ |

---

## 五、二轮 review 修复（2026-05-05 当晚）

Codex 复审本次修复后指出两个遗漏：

### P1：表格预处理破坏代码块

**症状**：`clean('```\\n│ foo\\nbar\\n```')` 当前输出 `│ foobar```` ——
代码块内含 `│` 的行被表格合并器误吞，且越过 closing fence。

**根因**：`_merge_wrapped_box_table_lines` 在 fenced code block 状态机之前运行，不知道自己在代码块里。

**修复**：在合并器内部添加 fence 状态跟踪，进入代码块后跳过合并；遇到 fence 标记也立即停止当前合并循环。

### P2：伪 frontmatter 仍会误删普通内容

**症状**：`---title: foo\\n这是普通段落\\n\\n正文` 被清成 `'正文'`，中间的普通段落被吞掉。

**根因**：标准 frontmatter 分支已加 YAML 校验，但伪 frontmatter（`---key: value` 同行式）分支仍只看首行像 key 就无条件删到第一个空行。

**修复**：把首行的 `---` 前缀剥离后，与后续行组成 body，复用 `_looks_like_yaml_frontmatter()` 校验。失败时只剥掉 `---` 前缀，正文保留。

### 二轮新增测试

- `test_box_char_in_code_block_preserved`
- `test_box_char_in_code_block_with_fence_marker`
- `test_table_outside_code_block_still_merges`
- `test_pseudo_frontmatter_with_prose_not_stripped`
- `test_pseudo_frontmatter_real_yaml_still_strips`

**测试结果**：139 → 144 passed。

---

## 六、待后续考虑（Codex 提议）

Codex 投资报告中还提了一个值得做但**不阻塞当前修复**的工程改进：

> 把 `_poll_loop()` 里那 5 个静默 `continue` 抽成 `classify_capture(raw, state) -> CaptureDecision`，返回明确的丢弃原因（`same_content` / `program_copy` / `no_format_artifacts` / `cleaned_empty` / `dedup_raw` / `dedup_cleaned`）。

**收益**：
- TUI 状态栏可以显示「为什么这次复制没进面板」
- 现场调试时不用猜是哪一关挡住的
- 也能为未来的 strict / balanced / capture-all 模式打基础

建议作为单独 PR 跟进。

---

## 七、改动清单

| 文件 | 改动 |
|------|------|
| `cleaner.py` | 新增 `_looks_like_yaml_frontmatter` + 重构 `_strip_frontmatter`；新增 `_merge_wrapped_box_table_lines` + 接入 `clean()` Step 2b |
| `tests/test_cleaner.py` | +12 个单元测试 |
| `tests/fixtures/frontmatter_false_positive_input.txt` | 新增 |
| `tests/fixtures/frontmatter_false_positive_expected.txt` | 新增 |
| `tests/fixtures/wrapped_box_table_input.txt` | 新增 |
| `tests/fixtures/wrapped_box_table_expected.txt` | 新增 |
| `tests/fixtures/wrapped_box_table_multicol_input.txt` | 新增 |
| `tests/fixtures/wrapped_box_table_multicol_expected.txt` | 新增 |
| `docs/FIX_SUMMARY_2026-05-05.md` | 本文件 |
