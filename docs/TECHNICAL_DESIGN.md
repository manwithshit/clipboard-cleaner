# Clipboard Cleaner — 技术方案文档

> 版本: v3 (2026-04-30)  
> 代码位置: `~/重要但不同步icloud/02_项目/github项目/clipboard-cleaner/`

---

## 1. 问题背景

在 macOS + Ghostty 终端中使用 Claude Code CLI 时，其 TUI 渲染器会主动在终端宽度处插入**硬换行符**（`\n`）和 **2 空格缩进**，而不是让终端自己做 soft-wrap。当窗口被 split pane 后，终端宽度变窄，硬换行更早发生，复制出来的内容更加支离破碎。

**具体表现：**

- 复制 Claude Code 输出时，换行符和缩进空格都会被一起带走
- 粘贴到微信/聊天框中时，文本格式支离破碎
- 此外还有引用竖线（`>`、`▎`、`|`）、ASCII 边框、尾空格等格式噪音
- Obsidian callout 标记（`[!tip]`、`[!note]` 等）在终端中不可见

这是 Claude Code 的已知 bug：[anthropics/claude-code#15199](https://github.com/anthropics/claude-code/issues/15199)

---

## 2. 设计目标

做一个 Python 小工具，后台监听系统剪贴板，自动捕获 Ghostty 中复制、鼠标选中、Command+A 全选带来的剪贴板变化，清洗内容后展示在一个 Ghostty pane 中。用户通过数字键快速复制清洗后的干净文本。

**核心原则：保守清洗，少误伤。** 默认不去破坏列表、代码块、表格和段落结构。只修复确定性强的问题。

---

## 3. 架构总览

```
┌─────────────────────┐     ┌──────────────────┐     ┌─────────────┐
│  系统剪贴板          │────>│ clipboard.py     │────>│ cleaner.py  │
│  pyperclip.paste()  │     │ 轮询 0.2s        │     │ 清洗管线     │
└─────────────────────┘     │ + 格式特征捕获      │     │ 7 步        │
                            │ + 反馈抑制         │     └──────┬──────┘
                            └──────┬─────────────┘            │
                                   │ queue.Queue              │
                                   ▼                          ▼
                            ┌──────────────────┐     ┌─────────────┐
                            │ tui.py           │<────│ model.py    │
                            │ curses 渲染       │     │ AppState    │
                            │ 按键+滚动处理      │     │ 历史 10 条   │
                            └──────────────────┘     └─────────────┘
```

### 线程模型

- **主线程**：curses TUI 渲染循环 + 键盘输入处理
- **后台线程**：每 0.2s 轮询系统剪贴板，清洗后推入 `queue.Queue(maxsize=20)`
- **通信**：`queue.Queue` 无锁，`AppState.history` 用 `threading.Lock` 保护

---

## 4. 清洗管线（7 步）

### 4.1 标准化换行符

```python
lines = raw_text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
```

### 4.2 去尾空格

所有行统一执行 `line.rstrip()`。

### 4.3 去行首装饰 + 嵌套引用处理

识别 `>`、`▎`、`|`、`｜`、`│` 等行首装饰字符：

```python
_NESTED_QUOTE = re.compile(r'^(\s*)((?:[│｜|>▎]\s*)+)')

def _strip_decorations(line: str) -> tuple[str, int]:
    # > text        → level 1, "text"
    # > > text      → level 2, "『text』"
    # ▎ ▎ ▎ text    → level 3, "『『text』』"
    # | | text      → level 2, "『text』"
    # | 表格行 |    → 原样保留（跳过）
```

表格行（`| col | col |`）被排除：如果行首装饰后的内容本身包含多个 `|` 分隔符且以 `|` 结尾，视为表格而非引用。

### 4.4 去公共缩进（仅普通段落）

```python
def _detect_common_indent(lines: list[str]) -> int:
    min_indent = min(len(l) - len(l.lstrip()) for l in non_blank)
    return min_indent
```

只对普通段落块执行，代码块和列表分别处理。

### 4.5 硬换行保守合并

**核心思路：「保留」规则优先**——默认合并，只在明确应该保留换行时保留。

```python
def _should_keep_break(prev_line: str, next_line: str) -> bool:
    # 保留的条件：
    # 1. 空行
    # 2. 上一行以强终止标点结尾（。！？.!?:：）
    # 3. 下一行是 Markdown 结构（```、##、- 、|、---）
    # 4. 下一行以大写字母开头且不是常见小词
    # 5. 下一行以数字+点开头
    # 其余情况一律合并
```

**中英文合并差异**：行末 CJK 字符 + 行首 CJK 字符 → 直接拼接；否则插入空格。

```python
last_cjk = '一' <= current[-1] <= '鿿'
first_cjk = '一' <= next_line[0] <= '鿿'
if last_cjk and first_cjk:
    current = current + next_line        # 中文不加空格
else:
    current = current + ' ' + next_line   # 英文加空格
```

### 4.6 压缩过多空行

3+ 个连续空行压成 2 个：`re.compile(r'\n{3,}')` → `\n\n`

### 4.7 去除首尾空行

`.strip()`。

---

## 5. 关键特性实现

### 5.1 Ghostty 选择捕获 + 格式特征过滤

**能力**：Ghostty 中用鼠标选中、Command+A 全选或复制 Claude Code 输出时，系统剪贴板会变化。工具会自动捕获这类终端选择内容，把它作为待清洗候选加入面板。

**边界**：为了避免语音输入、普通应用复制的干净文本频繁进入面板，仍会检测内容是否包含 Claude Code / 终端格式痕迹；没有痕迹的普通短文本会跳过。

```python
def has_format_artifacts(text: str) -> bool:
    """检测条件（满足任一即可）：
    1. 所有非空行有 ≥ 2 空格公共缩进
    2. 存在行首引用装饰（> 、| 、▎ 等）
    3. ASCII 边框整行
    4. 存在 trailing spaces（≥ 2 个行尾空格）
    5. 存在代码块围栏（``` 或 ~~~）
    """
```

效果：
- ✅ Ghostty 鼠标选中/Command+A 选中带硬换行或 2 空格续行的内容 → `True`，捕获
- ✅ Claude Code 输出「  这是缩进文本」→ `True`，捕获
- ✅ 语音输入「你好，这是语音输入的内容」→ `False`，跳过
- ✅ 其他应用复制的干净短文本 → `False`，跳过

### 5.2 反馈回路抑制

用户按数字键复制清洗结果到剪贴板后，监听线程会再次检测到新内容。通过时间窗抑制：

```python
# TUI 线程执行复制时：
state.mark_program_copy(item.cleaned)  # 记录程序写入内容的 hash
pyperclip.copy(item.cleaned)

# 后台线程轮询时：
if state.is_program_copy(current):  # 1.5 秒内且内容 hash 匹配时跳过
    continue
```

### 5.3 去重机制

双重 hash 检测：

```python
if item.raw_hash in self._recent_raw_hashes:
    return False  # 原始内容相同
if item.cleaned_hash in self._recent_cleaned_hashes:
    return False  # 清洗后相同（不同原始内容但清洗结果一样）
```

维护最近 50 条 hash，使用 `deque + set` 按插入顺序淘汰旧 hash，超出时保留最新一半。

### 5.4 列表项跨行延续

列表项的延续行（如 `    跨行延续`）被分类器识别为 `'normal'` 而非 `'list'`。通过后处理合并：

```python
# 分组后，如果 normal 组的所有非空行都是缩进的，且前一个组是 list，
# 则合并到 list 组
if (group_type == 'normal'
        and merged_groups
        and merged_groups[-1][0] == 'list'
        and all(not l.strip() or l.startswith((' ', '\t'))
                for l in group_lines if l.strip())):
    merged_groups[-1] = ('list', merged_groups[-1][1] + group_lines)
```

### 5.5 Block-aware 分组处理

内容按行类型分组，不同类型分别处理：

| 类型 | 处理方式 |
|------|----------|
| `code` | 去掉外层公共缩进，内部结构不动 |
| `list` | 去掉 ≥2 公共缩进，合并延续行 |
| `heading` | 去掉公共缩进 |
| `table` | Markdown pipe 表格转数字条目；解析失败则原样保留 |
| `blank` | 最多保留 1 个空行 |
| `normal` | 去公共缩进 + 硬换行合并 |

### 5.6 CJK 终端宽度处理

```python
def _cell_width(text: str) -> int:
    try:
        from wcwidth import wcswidth  # pip install wcwidth
        return wcswidth(text)
    except ImportError:
        pass
    # 回退：CJK 字符算 2 宽，其他算 1 宽
    return sum(2 if '一' <= c <= '鿿' else 1 for c in text)
```

---

## 6. 模块结构

```
clipboard-cleaner/
├── run.py           # 入口：python run.py (TUI) / python run.py --plain
├── model.py         # ClipboardItem + AppState（线程安全）
├── clipboard.py     # 剪贴板轮询 + 格式特征过滤 + 反馈抑制 + 去重
├── cleaner.py       # 清洗管线 + has_format_artifacts
├── tui.py           # curses TUI + CJK 宽度 + resize 自适应
├── .gitignore
└── tests/
    ├── test_cleaner.py          # 清洗单元测试
    ├── test_model.py            # 模型/状态测试
    ├── test_tui.py              # TUI 渲染辅助测试
    ├── test_golden_fixtures.py  # 6 组 golden fixture
    └── fixtures/                # 12 个 input/expected 对
```

### 文件大小

| 文件 | 行数 | 职责 |
|------|------|------|
| `cleaner.py` | ~430 | 清洗管线核心逻辑 |
| `tui.py` | ~270 | curses 渲染 + 按键 |
| `clipboard.py` | ~90 | 剪贴板轮询 |
| `model.py` | ~100 | 数据结构 + 线程安全状态 |
| `run.py` | ~60 | 入口 + 信号处理 |

### 外部依赖

| 库 | 用途 | 安装 |
|----|------|------|
| `pyperclip` | 跨平台剪贴板读写 | `pip install pyperclip` |
| `wcwidth` | CJK 字符终端宽度 | `pip install wcwidth` |
| `curses` | TUI 渲染 | Python 标准库 |

---

## 7. TUI 交互

```
┌──────────────────────────────┐
│   Clipboard Cleaner          │
├──────────────────────────────┤
│ [0] 清洗后的内容...           │
│                              │
│ [1] 另一条...                 │
│ ...                          │
│ [9] 最旧的...                 │
├──────────────────────────────┤
│ 监听中... 3/10               │
│ 0-9:复制  C:清空  q:退出     │
└──────────────────────────────┘
```

| 按键 | 行为 |
|------|------|
| `0`~`9` | 复制对应条目到系统剪贴板 |
| `↑` / `k` | 向上滚动历史内容 |
| `↓` / `j` | 向下滚动历史内容 |
| `PageUp` / `PageDown` | 按页滚动 |
| `Home` / `End` | 回到顶部 / 跳到底部 |
| `C` | 清空面板 |
| `q` | 退出（curses.wrapper 保证恢复终端） |

- 最新内容在 `[0]`，旧的依次往下
- 满 10 条时挤掉最旧的一条
- 历史内容按行滚动，长内容或 10 条历史超过屏幕高度时仍可查看
- 新内容进入时自动回到顶部显示最新条目
- 窗口 resize 自动重绘

---

## 8. 已知限制

1. **轮询不保证捕获极快连续复制**：0.2s 间隔内复制 A 再复制 B，只能看到 B
2. **不保证捕获无格式痕迹的 Claude Code 短输出**：如果 Claude Code 输出本身没有格式特征（如极短的一行），`has_format_artifacts` 会返回 False
3. **macOS Pasteboard 无 changeCount API**：pyperclip 只能用内容比较判断变化
4. **Windows/Linux 未测试**：当前以 macOS + Ghostty 为主

---

## 9. 演进历史（优化记录）

### v1 → v2（2026-04-29 → 2026-04-30）

| 优化项 | 变更 |
|--------|------|
| 不去除列表标记 | 审阅后改为保守清洗 |
| 硬换行判定 | 改为「保留规则」优先，不依赖终端宽度 |
| 反馈回路 | 新增 1.5s 抑制时间窗 |
| 嵌套引用 | 支持 `> >` → `『text』`、`▎ ▎` → `『text』` |
| 表格分隔符 | 修复被误删为边框的问题 |
| 列表延续行 | 修复跨行延续没被合并的问题 |
| 幽灵捕获 | 新增 `has_format_artifacts()` 过滤语音输入/Cmd+A |
| CJK-英文合并 | 智能加空格（CJK+CJK 不加） |
| Python 3.9 兼容 | `from __future__ import annotations` |

### v2 → v3（2026-04-30）

| 优化项 | 变更 |
|--------|------|
| Ghostty 选择捕获 | 将鼠标选中/Command+A 全选终端内容视为正式捕获能力 |
| TUI 滚动 | 新增按行/按页滚动，长历史不再被屏幕高度截断 |
| 表格处理 | Markdown pipe 表格转数字条目列表，保留含义、不保留表格结构 |
| 续行缩进 | 支持首行无缩进、后续 2 空格缩进的 Claude/Ghostty 硬换行样式 |
| Obsidian callout | 去除 `[!tip]`、`[!note]` 等终端不可见的 callout 标记 |

---

## 10. 测试策略

### 10.1 单元测试

覆盖所有清洗步骤的独立测试 + 边界条件：

- TC-CLEAN-001 ~ TC-CLEAN-012：换行标准化、缩进、列表、代码块、引用、换行合并、空行压缩
- 额外测试：空输入、单行、表格、列表延续、中英文混合、标题保护、去重

### 10.2 Golden Fixtures

`tests/fixtures/` 下维护 input/expected 对：

| 文件名 | 场景 |
|--------|------|
| `claude_paragraph` | 缩进段落 + 硬换行 |
| `claude_list` | 无序列表去缩进 |
| `claude_code_block` | 代码块保留内部缩进 |
| `quote_bar` | 引用竖线去除 |
| `chinese_wrap` | 中文硬换行合并 |
| `english_wrap` | 英文硬换行合并+补空格 |

每新增一条清洗规则，必须先补充 fixture。

### 10.3 端到端手工验收

1. Ghostty 窄 pane 中复制 Claude Code 输出
2. 确认面板出现清洗结果
3. 按数字键复制
4. 粘贴到微信验证格式

---

## 11. 运行方式

```bash
# TUI 模式（在 Ghostty pane 中运行）
clip

# 纯文本模式（pipe 测试）
echo '  缩进的文本' | python3 run.py --plain

# 运行测试
python3 -m pytest tests/ -v
```

Shell alias（`~/.zshrc`）：
```bash
alias clip='cd "$HOME/重要但不同步icloud/02_项目/github项目/clipboard-cleaner" && python3 run.py'
```
