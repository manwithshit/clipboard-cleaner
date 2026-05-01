# Clipboard Cleaner

> macOS 终端剪贴板清洗面板 — 把 Claude Code / Ghostty 复制出来的文本，自动整理成可以直接粘到**微信、飞书、Slack** 等聊天工具里的干净格式。

## 解决什么问题

在 Ghostty 终端里使用 Claude Code CLI 时，TUI 渲染器会主动在终端宽度处插入**硬换行**和 **2 空格缩进**。窗口被 split pane 后宽度更窄，复制出来的内容更碎。直接粘到微信/飞书会变成支离破碎的一堆碎片。

而且——微信和飞书**不渲染 Markdown**。Claude 输出的 `` `code` ``、`**加粗**`、`[链接](url)`、`## 标题`、` ```代码块``` ` 这些标记，在 IM 里全是字面字符，丑且难读。

这个工具会：

1. **自动**捕获你在 Ghostty 里复制 / 鼠标选中 / Cmd+A 全选的内容
2. **保守**清洗硬换行、引用竖线、缩进、ASCII 边框等终端格式噪音
3. 把 Markdown 行内标记**转成 IM 视觉等价物**：

   | 原始 | 清洗后 |
   |---|---|
   | `` `code` `` | `「code」` |
   | `**加粗**` | `【加粗】` |
   | `*斜体*` | `斜体` |
   | `[文字](url)` | `文字 (url)` |
   | `## 标题` | `【标题】` |
   | ` ```围栏``` ` | （围栏行去除，代码内容保留） |
   | Markdown 表格 | 数字条目列表 |
   | 水平分割线 `---` | 去除 |
   | YAML front-matter | 去除 |

4. 在 Ghostty pane 里展示最近 10 条清洗结果，按数字键 `0-9` 复制

> 这是 Claude Code 已知 bug 的 workaround：[anthropics/claude-code#15199](https://github.com/anthropics/claude-code/issues/15199)

## 演示

**输入**（从 Claude Code 复制）：

```
  ## 步骤

  请使用 `git commit` 提交，并 **不要** 跳过 hooks。
  详见 [文档](https://git-scm.com)。
```

**输出**（粘到微信里）：

```
【步骤】

请使用 「git commit」 提交，并 【不要】 跳过 hooks。
详见 文档 (https://git-scm.com)。
```

## 安装

```bash
git clone https://github.com/manwithshit/clipboard-cleaner.git
cd clipboard-cleaner
pip3 install pyperclip wcwidth
```

依赖：

- Python 3.9+
- macOS（依赖 `pbpaste`，跨平台未测试）
- 推荐在 [Ghostty](https://ghostty.org/) 终端的 split pane 中运行

## 使用

### TUI 模式（推荐）

```bash
python3 run.py
```

界面：

```
┌──────────────────────────────┐
│  Clipboard Cleaner           │
├──────────────────────────────┤
│ [0] 最新清洗结果...           │
│ [1] 上一条...                │
│ ...                          │
│ [9] 最旧的...                │
├──────────────────────────────┤
│ 监听中... 3/10               │
│ 0-9:复制 ↑↓:滚动 C:清空 q:退出│
└──────────────────────────────┘
```

| 按键 | 行为 |
|---|---|
| `0` ~ `9` | 复制对应条目到系统剪贴板 |
| `↑` / `k` | 向上滚动 |
| `↓` / `j` | 向下滚动 |
| `PageUp` / `PageDown` | 按页滚动 |
| `Home` / `End` | 跳到顶部 / 底部 |
| `C` | 清空面板 |
| `q` | 退出 |

### 纯文本模式（pipe 测试）

```bash
echo '  缩进的 **加粗** 文本' | python3 run.py --plain
```

### 推荐别名

在 `~/.zshrc` 加：

```bash
alias clip='cd /path/to/clipboard-cleaner && python3 run.py'
```

## 设计原则

**保守清洗，少误伤。** 默认不破坏列表、代码块、表格的内部结构，只修复确定性强的问题。

**IM 视觉等价。** 转换 Markdown 标记时，目标是"在不渲染 Markdown 的环境里读起来仍然有视觉强调"，而不是"语义无损的转换"。所以 `**bold**` → `【bold】` 是合理的，反过来不一定。

**幽灵捕获过滤。** 没有任何 Claude Code / 终端格式痕迹的文本（语音输入、其他应用复制的干净文本）会被跳过，不进面板。

## 架构

```
┌──────────────────┐    ┌─────────────────┐    ┌─────────────┐
│ pyperclip 轮询    │──▶│ has_format_     │──▶│ clean()     │
│ (0.2s)           │    │ artifacts() 过滤 │    │ 7 步管线    │
└──────────────────┘    └─────────────────┘    └──────┬──────┘
                                                     │ queue
                                                     ▼
                       ┌─────────────────┐    ┌─────────────┐
                       │ AppState        │◀──│ curses TUI   │
                       │ 历史 10 条       │    │ 数字键复制    │
                       └─────────────────┘    └─────────────┘
```

详见 [docs/TECHNICAL_DESIGN.md](docs/TECHNICAL_DESIGN.md)。

## 测试

```bash
python3 -m pytest tests/ -v
```

包含 88 个单元测试 + 6 组 golden fixture，覆盖所有清洗规则的常见和边界场景。

## 已知限制

1. 0.2s 轮询间隔内连续复制 A 再复制 B，只能看到 B
2. 没有任何格式痕迹的极短 Claude 输出会被 `has_format_artifacts` 跳过（设计取舍：宁愿漏，不要误捕获语音输入）
3. macOS only — Windows / Linux 未测试

## License

MIT
