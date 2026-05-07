# Clipboard Cleaner

**English** · [中文](README.zh-CN.md)

> A macOS clipboard cleaner panel for [Claude Code](https://claude.com/claude-code) / Ghostty users. Auto-strips the formatting artifacts (hard wraps, 2-space indents, quote bars, ASCII borders) that ruin every copy/paste from the terminal.

![UI demo](docs/images/ui-demo.png)

## Why this exists

If you use Claude Code CLI, you've almost certainly hit this:

> **Claude Code prepends a 2-space indent to every output line and inserts hard line breaks at ~80 characters.** These artifacts are baked into the clipboard. Every copy/paste needs manual cleanup.

This is a known and widely-reported bug — see the umbrella issue **[anthropics/claude-code#15199](https://github.com/anthropics/claude-code/issues/15199)** and its many duplicates ([#6827](https://github.com/anthropics/claude-code/issues/6827), [#859](https://github.com/anthropics/claude-code/issues/859), [#13378](https://github.com/anthropics/claude-code/issues/13378), and more, with hundreds of upvotes combined). Not yet fixed upstream.

**Where it bites globally** — the workflow disruption is the same regardless of language:

| Where you paste | The pain |
|---|---|
| **Slack / Discord** | Even though they render Markdown, the hard wraps shred code blocks on narrow screens — barely readable. |
| **GitHub PR / Issue comments** | `>` quote bars and stray spaces sneak in, looking unprofessional. |
| **Back into the terminal** | The worst case. A long command with hard wraps gets pasted as two lines, fails silently. |
| **Notion / Obsidian** | The 2-space indent gets misinterpreted as code blocks or block quotes — formatting is destroyed. |
| **VSCode** | Every paste needs Select All → Shift+Tab to manually remove the indent. |
| **WeChat / Feishu / Slack DMs** | Many IMs don't render Markdown at all, so `**bold**`, `` `code` ``, `## heading` show as literal characters — ugly and unreadable. |

The community workarounds (e.g., adding `"use \\ for line continuations"` to `CLAUDE.md`) **cost tokens on every session**. This project takes a different angle:

## How this tool solves it

1. **Background daemon** — runs in a Ghostty pane, polls the clipboard every 0.2s
2. **Smart capture** — only ingests text with terminal formatting fingerprints (hard wraps, indent, quote bars). Plain typing/voice input is ignored.
3. **Conservative cleaning** — strips hard wraps, quote bars, indents, ASCII borders. **Never destroys** the internal structure of code blocks, lists, or tables.
4. **Inline Markdown decoration transforms** — for messengers that don't render Markdown:

   | Original | Cleaned |
   |---|---|
   | `` `code` `` | `「code」` |
   | `**bold**` | `【bold】` |
   | `*italic*` | `italic` (markers removed) |
   | `[text](url)` | `text (url)` |
   | `## heading` | `【heading】` |
   | ` ```fenced``` ` | Fence removed, code body kept |
   | Markdown table | Numbered narrative items |
   | Box-drawing table `┌─┬─┐` | Same — converted to numbered items |
   | YAML front-matter | Removed |
   | Horizontal rule `---` | Removed |
   | Obsidian callout `[!tip]` | Label → `【label】` on its own line |

5. **History panel** — keeps the last 10 cleaned items. Press `0`–`9` to copy.

Full rules in [`docs/CLEANING_RULES.md`](docs/CLEANING_RULES.md).

## Demo

**Input** (copied from Claude Code):

```
  ## Steps

  Use `git commit` to commit, and **don't** skip the hooks.
  See the [docs](https://git-scm.com).
```

**Output** (paste-ready for any IM or note-taking app):

```
【Steps】

Use 「git commit」 to commit, and 【don't】 skip the hooks.
See the docs (https://git-scm.com).
```

## Install

```bash
git clone https://github.com/manwithshit/clipboard-cleaner.git
cd clipboard-cleaner
python3 -m pip install -r requirements-dev.txt
```

Requirements:

- Python 3.9+
- macOS (uses `pbpaste`; cross-platform untested)
- Best in a [Ghostty](https://ghostty.org/) split pane next to your Claude Code session

## Usage

### TUI mode (recommended)

```bash
python3 -m clipboard_cleaner.cli
```

| Key | Action |
|---|---|
| `0` – `9` | Copy that history item back to the clipboard |
| `↑` / `k` | Scroll up |
| `↓` / `j` | Scroll down |
| `PageUp` / `PageDown` | Page scroll |
| `Home` / `End` | Top / bottom |
| `C` | Clear panel |
| `q` | Quit |

### Plain mode (pipe testing)

```bash
echo '  indented **bold** text' | python3 -m clipboard_cleaner.cli --plain
```

### Recommended alias

In your `~/.zshrc`:

```bash
alias clip='cd /path/to/clipboard-cleaner && python3 -m clipboard_cleaner.cli'
```

## Design principles

- **Conservative cleaning, no collateral damage.** The default never breaks code blocks, lists, or tables — only fixes high-confidence noise.
- **IM-visual-equivalence.** When mapping Markdown markers, the goal is "still visually emphasized in plain-text contexts," not lossless conversion. So `**bold**` → `【bold】` is fine; it doesn't round-trip.
- **Ghost-capture filter.** Text with no terminal formatting fingerprints (voice input, normal app copies) is silently skipped — better miss than spam.

## Architecture

```
┌──────────────────┐    ┌─────────────────┐    ┌─────────────┐
│ clipboard/monitor│──▶│ has_format_     │──▶│ cleaner/    │
│ pyperclip 0.2s   │    │ artifacts() gate │    │ pipeline.py │
└──────────────────┘    └─────────────────┘    └──────┬──────┘
                                                     │ queue
                                                     ▼
                       ┌─────────────────┐    ┌─────────────┐
                       │ state.AppState  │◀──│ tui/app.py   │
                       │ history 10 max  │    │ digit-copy   │
                       └─────────────────┘    └─────────────┘
```

See [`docs/TECHNICAL_DESIGN.md`](docs/TECHNICAL_DESIGN.md) for details.

## Tests

```bash
python3 -m pytest tests/ -v
```

158 tests, including golden fixtures, cover the cleaning rules with common and edge cases.

## Known limitations

1. With a 0.2s poll interval, very rapid copy-A-then-copy-B sequences may miss A.
2. Extremely short Claude outputs with no formatting fingerprints get filtered out by design (preferring "miss" over "false-positive on voice input").
3. macOS-only — Windows / Linux untested.

## License

MIT
