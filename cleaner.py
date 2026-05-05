"""保守清洗管线。

默认清洗应该保守，不破坏列表、代码块、表格和段落结构。
只修复 Claude Code 复制文本中确定性较强的问题：
公共缩进、引用竖线、尾空格、明显的终端硬换行。
"""

from __future__ import annotations

import re
from typing import Literal

# --- 正则表达式 ---

# 行首装饰：引用竖线 | > ｜ │
_LINE_START_DECOR = re.compile(r'^(\s*)[│｜|>]\s+')

# ASCII / box drawing 边框整行（全由边框字符组成，≥ 3 字符）
_BORDER_CHARS = re.compile(
    r'^[─━│┃┌┏┐┓└┗┘┛├┝┤┞┟┠┡┢┣┤┥┦┧┨┩┪┫┬┭┮┯┰┱┲┳┴┵┶┷┸┹┺┻┼┽┾┿╀╁╂╃╄╅╆╇╈╉╊╋═║\s+\-+|+]*$'
)
_IS_BORDER = re.compile(
    r'^[─━│┃┌┏┐┓└┗┘┛├┝┤┥┨┩┪┫┬┭┮┯┰┱┲┳┴┵┶┷┸┹┺┻┼┽┾┿╀╁╂╃╄╅╆╇╈╉╊╋═║\s+\-+|]+$'
)

# 行内含 ≥ 3 个连续 box-drawing 字符（用于检测表格内任意行）
_BOX_DRAWING_RUN = re.compile(
    r'[─━│┃┌┏┐┓└┗┘┛├┝┤┞┟┠┡┢┣┤┥┦┧┨┩┪┫┬┭┮┯┰┱┲┳┴┵┶┷┸┹┺┻┼┽┾┿╀╁╂╃╄╅╆╇╈╉╊╋═║]{3,}'
)

# 中文（CJK Unified Ideographs）字符检测
_HAS_CJK = re.compile(r'[一-鿿]')

# Fenced code block 标记
_FENCE = re.compile(r'^\s*(```|~~~)')

# 列表行
_UNORDERED_LIST = re.compile(r'^(\s*)([-*•])\s')
_ORDERED_LIST = re.compile(r'^(\s*)\d+[.、)\]]\s')

# 标题行
_HEADING = re.compile(r'^#{1,6}\s+')

# 表格行（| 开头且包含至少一个 | 分隔符）
_TABLE_ROW = re.compile(r'^\s*\|.*\|')

# 强终止标点（中英文句号、问号、感叹号、冒号后接空行）
_STRONG_TERMINATOR = re.compile(r'[。！？.!?:：]$')

# 连续空行（3+ 个压成 2 个）
_MULTI_BLANK = re.compile(r'\n{3,}')

# 单个字符的行（可能是截断产物，但不合并）
_SINGLE_CHAR_LINE = re.compile(r'^.{0,2}$')

# --- IM 模式行内标记转换 ---
# 微信/飞书等 IM 不渲染 Markdown，行内 ** / * / ` / [](url) 都是字面字符，
# 阅读体验差。以下规则把它们转成 IM 中视觉等价的中文符号。

_INLINE_CODE = re.compile(r'`([^`\n]+)`')
_BOLD_STAR = re.compile(r'\*\*([^*\n]+?)\*\*')
_BOLD_UNDER = re.compile(r'__([^_\n]+?)__')
_LINK = re.compile(r'\[([^\]\n]+)\]\(([^)\n]+)\)')
_ITALIC_STAR = re.compile(r'(?<![\*\w])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\*\w])')
_ITALIC_UNDER = re.compile(r'(?<![_\w])_(?!\s)([^_\n]+?)(?<!\s)_(?![_\w])')
_HEADING_LINE = re.compile(r'^(\s*)#{1,6}\s+(.+?)\s*#*\s*$')

# 占位符用的私有 Unicode 区段，不会出现在正常文本中
_PLACEHOLDER_OPEN = ''
_PLACEHOLDER_CLOSE = ''

BlockType = Literal['code', 'list', 'heading', 'table', 'quote', 'blank', 'normal']


def _transform_inline(text: str) -> str:
    """把行内 Markdown 标记转成 IM 视觉等价物。

    顺序：先用占位符保护反引号内的内容，再处理 bold/link/italic，
    最后把占位符还原为「」。这样可以避免 *italic* 误伤反引号内的星号。
    """
    if not text:
        return text

    # Step 1: 保护反引号内的内容
    stash: list[str] = []

    def _stash(match: 're.Match[str]') -> str:
        stash.append(match.group(1))
        return f'{_PLACEHOLDER_OPEN}{len(stash) - 1}{_PLACEHOLDER_CLOSE}'

    text = _INLINE_CODE.sub(_stash, text)

    # Step 2: bold（必须在 italic 之前，否则 ** 会被 * 吃掉）
    text = _BOLD_STAR.sub(r'【\1】', text)
    text = _BOLD_UNDER.sub(r'【\1】', text)

    # Step 3: 链接 [文字](url) → 文字 (url)
    text = _LINK.sub(r'\1 (\2)', text)

    # Step 4: italic（去星号/下划线，留文字）
    text = _ITALIC_STAR.sub(r'\1', text)
    text = _ITALIC_UNDER.sub(r'\1', text)

    # Step 5: 还原反引号内的内容为「」
    def _restore(match: 're.Match[str]') -> str:
        idx = int(match.group(1))
        return f'「{stash[idx]}」'

    text = re.sub(
        f'{_PLACEHOLDER_OPEN}(\\d+){_PLACEHOLDER_CLOSE}',
        _restore,
        text,
    )

    return text


def _transform_heading_line(line: str) -> str:
    """把 `## 标题` 转成 `【标题】`。保留行首缩进。"""
    match = _HEADING_LINE.match(line)
    if not match:
        return line
    indent, title = match.group(1), match.group(2)
    return f'{indent}【{title}】'


def _classify_line(line: str, in_code_block: bool) -> BlockType:
    """判断行的类型。"""
    if in_code_block:
        return 'code'

    stripped = line.strip()
    if not stripped:
        return 'blank'

    if _FENCE.match(stripped):
        return 'code'

    if _HEADING.match(stripped):
        return 'heading'

    if _TABLE_ROW.match(line):
        return 'table'

    if _UNORDERED_LIST.match(line) or _ORDERED_LIST.match(line):
        return 'list'

    return 'normal'


# 行首装饰：引用竖线 | > ｜ │ ▎（支持多层嵌套）
# ▎ (U+258E LEFT ONE QUARTER BLOCK) 是 Claude Code 的实际引用标记
# 匹配形式：> text, > > text, | | text, ｜ ｜ text, ▎ text, ▎ ▎ text 等
# 装饰字符后**至多吃 1 个空格**（之前是 \s* 太贪婪，会把代码缩进等内容
# 空格也吃掉，比如 `▎     return x` 中的 4 空格代码缩进）
_NESTED_QUOTE = re.compile(r'^(\s*)((?:[│｜|>▎] ?)+)')

# 单个装饰字符（用于计算嵌套层级）
_SINGLE_DECOR = re.compile(r'[│｜|>▎]\s*')

# 引用层级标记：1 层 → 〔引〕，2 层 → 〔引²〕，3 层 → 〔引³〕...
# 用上标数字而非串接『 』，避免深层嵌套时一堆括号视觉混乱
_SUPERSCRIPT_TRANS = str.maketrans('0123456789', '⁰¹²³⁴⁵⁶⁷⁸⁹')
_INVERSE_SUPERSCRIPT_TRANS = str.maketrans('⁰¹²³⁴⁵⁶⁷⁸⁹', '0123456789')
_QUOTE_MARKER_RE = re.compile(r'^〔引([⁰¹²³⁴⁵⁶⁷⁸⁹]*)〕')


def _format_quote_marker(level: int) -> str:
    """生成 〔引〕/〔引²〕/〔引³〕... 标记。"""
    if level <= 0:
        return ''
    if level == 1:
        return '〔引〕'
    return f'〔引{str(level).translate(_SUPERSCRIPT_TRANS)}〕'

# Obsidian callout / admonition 标记：[!tip]、[!note]、[!warning] 等
# 终端中无法渲染，清洗时把整行转成 `## 标签`（再由 heading 处理转 【标签】）
_OBSIDIAN_CALLOUT = re.compile(r'^\[![a-zA-Z]+\]\s*')


# Claude Code 终端输出的前缀标记（⏺ ⎿）— 复制时会跟着进剪贴板，
# 这是 Claude Code TUI 自己加的"输出气泡 bullet"，对 IM 粘贴毫无用处。
_CC_PREFIX_MARKER = re.compile(r'^([⏺⎿])\s*')

# YAML front-matter 检测
# 标准形式：---\nkey: value\n---
# 伪形式：---  key: value 或 ---key: value（GPT/Claude 偶尔输出）
# 允许行首有空格（Claude Code 输出常带 2 空格缩进）
_FRONTMATTER_DELIM = re.compile(r'^\s*---\s*$')
_PSEUDO_FRONTMATTER_HEAD = re.compile(r'^\s*---\s*["\']?[\w-]+["\']?\s*:')

# YAML key:value 行：可选引号 + 标识符 + 冒号
_YAML_KEY_LINE = re.compile(r'^\s*["\']?[\w.\-]+["\']?\s*:')
# YAML 续行（缩进开头，允许 - 列表项 / 引号 / 普通字符）
_YAML_CONT_LINE = re.compile(r'^\s+\S')
# YAML 注释行
_YAML_COMMENT_LINE = re.compile(r'^\s*#')


def _strip_cc_prefix(lines: list[str]) -> list[str]:
    """去除 Claude Code 输出行的前缀标记 ⏺ / ⎿。"""
    return [_CC_PREFIX_MARKER.sub('', line) for line in lines]


def _looks_like_yaml_frontmatter(body_lines: list[str]) -> bool:
    """判断 `---` 包围的内容是否真的是 YAML front-matter。

    要求：
    - 至少有一个 key:value 行
    - 除了 key:value、缩进续行、注释、空行外，没有其他类型的内容
      （否则可能是普通文本被两个 `---` 包住，应作为水平分割线处理）
    """
    if not body_lines:
        return False

    has_key_value = False
    last_was_key = False

    for line in body_lines:
        stripped = line.strip()
        if not stripped:
            last_was_key = False
            continue
        if _YAML_COMMENT_LINE.match(line):
            continue
        if _YAML_KEY_LINE.match(line):
            has_key_value = True
            last_was_key = True
            continue
        # 缩进续行只在前一行是 key 时合法
        if last_was_key and _YAML_CONT_LINE.match(line):
            continue
        # 出现非 YAML 形态的内容，整体视为非 frontmatter
        return False

    return has_key_value


def _strip_frontmatter(lines: list[str]) -> list[str]:
    """剥离文本开头的 YAML front-matter（标准或伪格式）。

    标准：第一行是 `---`，到下一行 `---` 之间整段消除（含两个分隔符）。
            **仅当中间内容真的看起来像 YAML 时**才剥离，避免把 `---\\n正文\\n---`
            这种水平分割块误吃掉。
    伪格式：第一行是 `---  title: "..."`（GPT 误把 `---` 和首字段写一行），
            从该行开始消除直到第一个空行（含开头那行）。
    """
    if not lines:
        return lines

    # 标准 YAML
    if _FRONTMATTER_DELIM.match(lines[0].strip()):
        for i in range(1, len(lines)):
            if _FRONTMATTER_DELIM.match(lines[i].strip()):
                body = lines[1:i]
                if _looks_like_yaml_frontmatter(body):
                    return lines[i + 1:]
                # 不是 YAML，去掉首尾两个 `---`，正文保留
                return body + lines[i + 1:]
        # 没找到收尾分隔符，保持原样
        return lines

    # 伪 front-matter：--- 跟在同一行的 key: value
    if _PSEUDO_FRONTMATTER_HEAD.match(lines[0]):
        # 找到第一个空行作为 frontmatter 终止
        end = len(lines)
        for i in range(1, len(lines)):
            if not lines[i].strip():
                end = i
                break

        # 把首行的 `---` 前缀剥离后，与后续行组成 body 做 YAML 校验
        first_line_body = re.sub(r'^\s*---\s*', '', lines[0])
        body = [first_line_body] + list(lines[1:end])

        if _looks_like_yaml_frontmatter(body):
            # 真 YAML：消除整段 frontmatter
            if end < len(lines):
                return lines[end + 1:]
            return []

        # body 不像纯 YAML：只剥掉首行的 `---` 前缀，正文保留
        return [first_line_body] + lines[1:]

    return lines


def _process_callout(text: str) -> str:
    """把 `[!type] 标签文字` 转成 `## 标签文字`，纯标记则返回空字符串。

    转成 `## ` 是为了后续 heading 分类把它正确包成 `【 】` 并独立成行，
    不被合并到下一行内容里。
    """
    match = _OBSIDIAN_CALLOUT.match(text)
    if not match:
        return text
    label = text[match.end():].strip()
    if label:
        return '## ' + label
    return ''

_CODE_DECOR = re.compile(r'^(\s*)((?:[│｜|>▎] ?)+)(.*)$')


def _strip_decorations(line: str) -> tuple[str, int]:
    """去除行首装饰竖线/大于号，返回 (处理后的行, 嵌套层级)。

    嵌套规则（统一标记 〔引ⁿ〕）：
      > 文本        → level 1, "〔引〕文本"
      > > 文本      → level 2, "〔引²〕文本"
      > > > 文本    → level 3, "〔引³〕文本"
      | 文本        → 同理（其他装饰字符走相同路径）

    例外：装饰后的内容是 Markdown 结构（代码围栏/标题/列表/表格）时，
    不加标记，让分类器正常识别那些结构。
    """
    stripped = line.strip()

    # 先尝试匹配嵌套引用模式：行首连续的装饰字符（> > | ｜ │）
    # 这样可以把 `| | text` 识别为引用而非表格
    quote_match = _NESTED_QUOTE.match(line)
    if quote_match:
        decor = quote_match.group(2)
        # 判断装饰后的剩余内容是否像表格（有 | 分隔的多列）
        rest_after_decor = line[quote_match.end():]
        rest_stripped = rest_after_decor.strip()
        # 如果装饰后的内容本身包含 | 分隔符（像表格），跳过
        # 例如 `| col | col |` → decor 只是第一个 `|`，rest 是 `col | col |`
        # 但如果 decor 覆盖了全部装饰（如 `| | text`），rest 就是纯文本
        if rest_stripped.count('|') >= 1 and rest_stripped.endswith('|'):
            # 剩余部分像表格，整行当表格处理
            return line, 0

        indent = quote_match.group(1)
        level = len(_SINGLE_DECOR.findall(decor))
        rest = rest_after_decor

        # Obsidian callout：[!tip] 标签 → ## 标签（独立成行，丢弃引用层级）
        if _OBSIDIAN_CALLOUT.match(rest.lstrip()):
            rest = _process_callout(rest.lstrip())
            return indent + rest, level

        # 结构性内容（围栏/标题/列表/表格）不加 〔引〕 标记，
        # 让 _classify_line 正常识别这些结构
        rest_lstripped = rest.lstrip()
        is_structural = bool(
            _FENCE.match(rest_lstripped)
            or _HEADING.match(rest_lstripped)
            or _UNORDERED_LIST.match(rest_lstripped)
            or _ORDERED_LIST.match(rest_lstripped)
            or rest_lstripped.startswith('|')
        )
        if is_structural:
            return indent + rest, level

        # 普通引用文本：加 〔引ⁿ〕 标记
        marker = _format_quote_marker(level)
        return indent + marker + rest, level

    # 表格行：两端有 | 且中间有 | 分隔符
    if stripped.startswith('|') and stripped.endswith('|') and len(stripped) > 2:
        return line, 0
    if stripped.count('|') >= 2:
        return line, 0

    # 裸 Obsidian callout：[!tip] 标签 → ## 标签
    if _OBSIDIAN_CALLOUT.match(stripped):
        return _process_callout(stripped), 0

    return line, 0


def _strip_code_decorations(line: str) -> tuple[str, int]:
    """去除代码块外层装饰，但保留代码自身缩进。"""
    match = _CODE_DECOR.match(line)
    if not match:
        return line, 0

    indent, decor, rest = match.groups()
    level = len(re.findall(r'[│｜|>▎]', decor))
    return indent + rest, level


def _is_border_line(line: str) -> bool:
    """判断是否整行都是 ASCII / box drawing 边框字符。

    注意：Markdown 表格分隔行（如 |------|------|）不是边框，
    需要跳过。判断标准：以 | 开头且以 | 结尾的行视为表格行。
    """
    stripped = line.strip()
    if len(stripped) < 3:
        return False

    # 跳过表格分隔行：|---|---| 格式
    if stripped.startswith('|') and stripped.endswith('|'):
        return False

    return bool(_IS_BORDER.match(stripped))


def _should_keep_break(prev_line: str, next_line: str) -> bool:
    """判断两个相邻行之间的换行是否应该保留。

    保守策略：默认合并，只在明确应该保留时保留。
    """
    prev_stripped = prev_line.strip()
    next_stripped = next_line.strip()

    # 空行永远保留
    if not prev_stripped or not next_stripped:
        return True

    # 上一行以强终止标点结尾 → 保留换行
    if _STRONG_TERMINATOR.search(prev_stripped):
        return True

    # 下一行是 Markdown 结构符号 → 保留
    if (_FENCE.match(next_stripped)
            or _HEADING.match(next_stripped)
            or _UNORDERED_LIST.match(next_line)
            or _ORDERED_LIST.match(next_line)
            or next_stripped.startswith('|')
            or next_stripped.startswith('- - -')
            or next_stripped.startswith('---')):
        return True

    # CJK 中文段落里的硬换行：上一行以 CJK 字符结尾且没有强终止标点
    # → 合并（即使下一行以英文大写字母开头，例如 "详见这个\nGitHub Issue"）
    last_char = prev_stripped[-1]
    if '一' <= last_char <= '鿿':
        return False

    # 下一行以大写字母开头（英文新句子的可能性）→ 保留
    if next_stripped[0].isupper() and len(next_stripped) > 1:
        # 但如果是小词（the, a, is 等）则可能是硬换行，合并
        lower_first = next_stripped.split()[0].lower() if next_stripped.split() else ''
        if lower_first not in ('the', 'a', 'an', 'is', 'are', 'was', 'were', 'it', 'this',
                               'that', 'for', 'and', 'but', 'or', 'not', 'have', 'has', 'had',
                               'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may',
                               'might', 'must', 'can', 'with', 'without', 'from', 'by', 'at',
                               'on', 'in', 'of', 'to'):
            return True

    # 下一行以数字+点开头（可能是有序列表，但没被识别到）→ 保留
    if re.match(r'^\d+\.\s', next_stripped):
        return True

    # 上一行很短（≤ 3 字符）且下一行也很短 → 可能是被截断，合并
    if len(prev_stripped) <= 3 and len(next_stripped) <= 3:
        return False

    # 默认：合并（硬换行）
    return False


def _is_cjk_or_punctuation(char: str) -> bool:
    """判断字符是否适合按 CJK 文本直接拼接。"""
    return (
        '一' <= char <= '鿿'
        or char in '，。！？；：、）】』」》〉’”'
    )


def _merge_hard_wraps(lines: list[str]) -> list[str]:
    """在普通段落块内保守合并硬换行。

    返回合并后的行列表。
    """
    if not lines:
        return []

    result: list[str] = []
    current = lines[0]

    for i in range(1, len(lines)):
        next_line = lines[i]

        if _should_keep_break(current, next_line):
            result.append(current)
            current = next_line
        else:
            # 合并：如果当前行以 CJK 结尾且下一行以 CJK 开头，不加空格
            if current and next_line:
                first_cjk = _is_cjk_or_punctuation(next_line[0])
                last_ascii_alpha = current[-1].isascii() and current[-1].isalpha()
                if first_cjk and not last_ascii_alpha:
                    current = current + next_line
                elif current[-1] != ' ' and next_line[0] != ' ':
                    current = current + ' ' + next_line
                else:
                    current = current + next_line
            else:
                current = current + next_line

    result.append(current)
    return result


def _unwrap_nested_quote(line: str) -> tuple[str, int]:
    """识别 `〔引〕` / `〔引²〕` / `〔引³〕` 等标记，返回 (剥标记后的文本, level)。

    没有标记则返回 (text, 0)。
    """
    stripped = line.strip()
    match = _QUOTE_MARKER_RE.match(stripped)
    if not match:
        return stripped, 0
    sup = match.group(1)
    if not sup:
        level = 1
    else:
        level = int(sup.translate(_INVERSE_SUPERSCRIPT_TRANS))
    return stripped[match.end():], level


def _merge_nested_quote_group(lines: list[str]) -> list[str]:
    """合并引用组：同层级的连续行先按硬换行规则合并，整段重加一次 〔引ⁿ〕。

    无标记的行（level=0）保持不变。
    """
    pairs = [_unwrap_nested_quote(l) for l in lines if l.strip()]
    if not pairs:
        return []

    result: list[str] = []
    i = 0
    while i < len(pairs):
        text, level = pairs[i]
        if level == 0:
            result.append(text)
            i += 1
            continue
        # 收集连续同层级的非空行
        chunk = [text]
        j = i + 1
        while j < len(pairs) and pairs[j][1] == level:
            chunk.append(pairs[j][0])
            j += 1
        # 用硬换行规则合并
        merged = _merge_hard_wraps(chunk)
        marker = _format_quote_marker(level)
        for m in merged:
            result.append(marker + m)
        i = j
    return result


def _detect_common_indent(lines: list[str]) -> int:
    """检测一组行的最小公共缩进。"""
    min_indent = float('inf')
    for line in lines:
        if line.strip():  # 跳过空行
            stripped = len(line) - len(line.lstrip())
            min_indent = min(min_indent, stripped)
    return min_indent if min_indent != float('inf') else 0


def _remove_common_indent(lines: list[str], indent: int) -> list[str]:
    """去掉指定宽度的公共缩进。"""
    if indent <= 0:
        return lines

    result = []
    for line in lines:
        if line.strip():
            result.append(line[indent:] if len(line) >= indent else line.lstrip())
        else:
            result.append('')
    return result


def _remove_continuation_indent(lines: list[str]) -> list[str]:
    """去掉首行无缩进、后续硬换行行带 2 空格的终端缩进。"""
    if len(lines) < 2:
        return lines

    first_indent = len(lines[0]) - len(lines[0].lstrip(' '))
    if first_indent != 0:
        return lines

    continuation_lines = [line for line in lines[1:] if line.strip()]
    if not continuation_lines:
        return lines

    continuation_indents = [
        len(line) - len(line.lstrip(' ')) for line in continuation_lines
    ]
    if min(continuation_indents) < 2:
        return lines

    return [lines[0]] + [
        line[2:] if line.startswith('  ') else line for line in lines[1:]
    ]


def _split_markdown_table_row(line: str) -> list[str] | None:
    """拆分 Markdown pipe 表格行。"""
    stripped = line.strip()
    if not stripped.startswith('|') or not stripped.endswith('|'):
        return None

    return [cell.strip() for cell in stripped.strip('|').split('|')]


def _is_markdown_table_separator(cells: list[str]) -> bool:
    """判断是否为 Markdown 表格分隔行。"""
    if not cells:
        return False
    for cell in cells:
        compact = cell.replace(' ', '')
        if not re.fullmatch(r':?-{3,}:?', compact):
            return False
    return True


def _normalize_table_cell(cell: str) -> str:
    """规范化表格单元格内容，保持语义优先。"""
    return re.sub(r'\s+', ' ', cell.replace('<br>', '；').replace('<br/>', '；')).strip()


def _rows_to_narrative(headers: list[str], data_rows: list[list[str]]) -> list[str] | None:
    """把表头 + 数据行组合成数字条目列表。"""
    headers = [
        header if header else f'列{i + 1}' for i, header in enumerate(headers)
    ]
    if not headers:
        return None

    result: list[str] = []
    item_index = 1
    for row in data_rows:
        cells = [_normalize_table_cell(cell) for cell in row]
        if len(cells) > len(headers):
            cells = cells[:len(headers) - 1] + [' '.join(cells[len(headers) - 1:])]
        elif len(cells) < len(headers):
            cells = cells + [''] * (len(headers) - len(cells))

        fields = [
            (header, cell)
            for header, cell in zip(headers, cells)
            if cell
        ]
        if not fields:
            continue

        if result:
            result.append('')
        first_header, first_cell = fields[0]
        result.append(f'{item_index}. {first_header}：{first_cell}')
        for header, cell in fields[1:]:
            result.append(f'   {header}：{cell}')
        item_index += 1

    return result if result else None


def _table_to_narrative(lines: list[str]) -> list[str] | None:
    """把规整 Markdown pipe 表格转成数字条目列表。"""
    rows = [_split_markdown_table_row(line) for line in lines if line.strip()]
    if any(row is None for row in rows) or len(rows) < 3:
        return None

    parsed_rows = [row for row in rows if row is not None]
    headers = [_normalize_table_cell(cell) for cell in parsed_rows[0]]
    if not _is_markdown_table_separator(parsed_rows[1]):
        return None

    return _rows_to_narrative(headers, parsed_rows[2:])


# Box-drawing 表格识别
_BOX_DATA_OPEN = set('│┃')          # 数据行的左右边界
_BOX_BORDER_OPEN = set('┌┏├┝└┗')   # 上/中/下边框的起始字符
_BOX_BORDER_CLOSE = set('┐┓┤┥┘┛')  # 上/中/下边框的结束字符
_BOX_BORDER_INNER = set(
    '─━═│┃┌┏┐┓└┗┘┛├┝┤┥┨┩┪┫┬┭┮┯┰┱┲┳┴┵┶┷┸┹┺┻'
    '┼┽┾┿╀╁╂╃╄╅╆╇╈╉╊╋║'
)


def _is_box_table_line(line: str) -> bool:
    """判断是否是 box-drawing 表格的数据行或边框行。

    数据行：│ a │ b │ 形式（U+2502 或 U+2503 包裹）
    边框行：┌─┬─┐ / ├─┼─┤ / └─┴─┘ 形式
    """
    stripped = line.strip()
    if len(stripped) < 3:
        return False

    first, last = stripped[0], stripped[-1]

    # 数据行
    if first in _BOX_DATA_OPEN and last in _BOX_DATA_OPEN:
        return True

    # 边框行
    if first in _BOX_BORDER_OPEN and last in _BOX_BORDER_CLOSE:
        # 整行只能由边框字符 + 空白组成
        return all(c in _BOX_BORDER_INNER or c.isspace() for c in stripped)

    return False


_BOX_TABLE_OPENERS = _BOX_DATA_OPEN | _BOX_BORDER_OPEN
_BOX_TABLE_CLOSERS = _BOX_DATA_OPEN | _BOX_BORDER_CLOSE


_NEW_ROW_STARTERS = frozenset('┌┏├┝└┗')  # 新表格行的起始字符


def _merge_wrapped_box_table_lines(lines: list[str]) -> list[str]:
    """合并被终端窄度折断的 box-drawing 表格碎片行。

    场景 1：`│ 林黛玉 │ 多愁善感 │` 因终端列宽不足被折成
        ``│ 林黛玉 │`` + ``多愁善感 │``
    场景 2：``┌─────`` 后接 ``─────┐`` 这种边框行被折断
    场景 3：``│ 人物 │ 性格`` 后接 ``            │`` 这种孤立续行

    策略：
    - 当前行以表格 opener 开头时进入合并流程
    - 如果当前未形成完整表格行，**必须**吞并下一行；
    - 如果当前已完整，只在下一行明显是「续行碎片」时才继续吞并
      （不能以新行起始字符 ┌├└ 开头，且不是独立完整表格行）

    重要：跳过 fenced code block 内容，避免误吞代码行。
    """
    if len(lines) < 2:
        return lines

    result: list[str] = []
    i = 0
    in_code_block = False
    code_fence_char: str | None = None

    while i < len(lines):
        line = lines[i]

        # 跟踪 fenced code block 状态
        fence_match = _FENCE.match(line.strip())
        if fence_match:
            char = fence_match.group(1)[0]
            if not in_code_block:
                in_code_block = True
                code_fence_char = char
            elif code_fence_char == char:
                in_code_block = False
                code_fence_char = None
            result.append(line)
            i += 1
            continue

        # 在代码块内部时不做表格合并
        if in_code_block:
            result.append(line)
            i += 1
            continue

        stripped = line.lstrip()

        if not stripped or stripped[0] not in _BOX_TABLE_OPENERS:
            result.append(line)
            i += 1
            continue

        leading_indent = line[:len(line) - len(stripped)]
        merged_body = stripped
        is_complete = _is_box_table_line(leading_indent + merged_body)
        j = i + 1
        max_lookahead = 5

        while j < len(lines) and (j - i) <= max_lookahead:
            next_line = lines[j]
            next_stripped = next_line.strip()

            if not next_stripped:
                break
            # 下一行本身已是完整表格行 → 是新行，不合并
            if _is_box_table_line(next_line):
                break
            # 下一行是 fence → 不能跨代码块边界合并
            if _FENCE.match(next_stripped):
                break

            if is_complete:
                # 当前已完整：只在下一行是续行碎片时继续合并
                # 排除以新行起始字符开头的（那是新行碎片）
                if next_stripped[0] in _NEW_ROW_STARTERS:
                    break
                # 续行特征：末尾是 closer，或整行仅由 box+空白构成
                is_continuation = (
                    next_stripped[-1] in _BOX_TABLE_CLOSERS or
                    all(c in _BOX_BORDER_INNER or c.isspace()
                        for c in next_stripped)
                )
                if not is_continuation:
                    break

            # 吞并
            merged_body = merged_body.rstrip() + next_stripped
            j += 1
            is_complete = _is_box_table_line(leading_indent + merged_body)

        result.append(leading_indent + merged_body)
        i = j

    return result


def _box_table_to_narrative(lines: list[str]) -> list[str] | None:
    """把 box-drawing 表格转成数字条目列表。"""
    data_rows: list[list[str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # 跳过纯边框行
        if stripped[0] in _BOX_BORDER_OPEN and stripped[-1] in _BOX_BORDER_CLOSE:
            continue
        # 数据行：把 │ ┃ 都规范化成 |
        if stripped[0] in _BOX_DATA_OPEN and stripped[-1] in _BOX_DATA_OPEN:
            normalized = re.sub(r'[│┃]', '|', stripped)
            cells = [c.strip() for c in normalized.strip('|').split('|')]
            if cells:
                data_rows.append(cells)

    if len(data_rows) < 2:
        return None

    headers = [_normalize_table_cell(c) for c in data_rows[0]]
    body = data_rows[1:]
    return _rows_to_narrative(headers, body)


def clean(raw_text: str) -> str:
    """保守清洗管线主入口。

    1. 标准化换行符
    2. 分块识别 + 去除尾空格
    3. 去除行首装饰 + 边框整行
    4. 普通段落：去公共缩进 + 保守合并硬换行
    5. 压缩过多空行
    6. 去除首尾空行
    """
    if not raw_text or not raw_text.strip():
        return ''

    # Step 1: 标准化换行符
    lines = raw_text.replace('\r\n', '\n').replace('\r', '\n').split('\n')

    # Step 1a: 去除 Claude Code 输出前缀标记（⏺ ⎿）
    lines = _strip_cc_prefix(lines)

    # Step 1b: 剥离开头的 YAML front-matter（IM 不需要 metadata）
    lines = _strip_frontmatter(lines)

    # Step 2: 去尾空格（所有行）
    lines = [line.rstrip() for line in lines]

    # Step 2b: 合并被窄终端折断的 box-drawing 表格行
    # 必须在分类前，否则碎片会被 _strip_decorations 当成引用块加 〔引〕
    lines = _merge_wrapped_box_table_lines(lines)

    # Step 3: 识别并处理各行
    in_code_block = False
    code_fence_char = None
    code_block_decorated = False

    # 分组：连续的同类型行归为一组
    groups: list[tuple[BlockType, list[str]]] = []
    current_group_type: BlockType | None = None
    current_group_lines: list[str] = []

    for line in lines:
        quote_level = 0

        # 先去掉终端/Claude 引用装饰，再分类。若代码块是从带装饰的
        # 区域打开的，代码块内部也继续剥掉同类装饰。
        if in_code_block:
            if code_block_decorated:
                line, quote_level = _strip_code_decorations(line)
            line_type = _classify_line(line, in_code_block)
        elif _is_box_table_line(line):
            # Box-drawing 表格（│ data │ 或 ┌─┬─┐）优先级最高：
            # 跳过引用剥离和边框删除，直接进入 table 组让后续转条目
            line_type = 'table'
        else:
            line, quote_level = _strip_decorations(line)

            # 去掉边框整行
            if _is_border_line(line):
                line = ''

            line_type = _classify_line(line, in_code_block)

            if quote_level >= 1 and line_type == 'normal':
                line_type = 'quote'

        # 处理 fenced code block 边界
        if line_type == 'code' and _FENCE.match(line.strip()):
            fence_match = _FENCE.match(line.strip())
            if fence_match:
                char = fence_match.group(1)[0]
                if not in_code_block:
                    in_code_block = True
                    code_fence_char = char
                    code_block_decorated = quote_level > 0
                elif code_fence_char == char:
                    in_code_block = False
                    code_fence_char = None
                    code_block_decorated = False

        # 分组
        if line_type != current_group_type:
            if current_group_type is not None:
                groups.append((current_group_type, current_group_lines))
            current_group_type = line_type
            current_group_lines = [line]
        else:
            current_group_lines.append(line)

    # 收尾
    if current_group_type is not None:
        groups.append((current_group_type, current_group_lines))

    # 合并列表项的跨行延续
    # 例如：list -> normal(缩进文本) -> list → normal 合并到前面的 list
    merged_groups: list[tuple[BlockType, list[str]]] = []
    for group_type, group_lines in groups:
        if (group_type == 'normal'
                and merged_groups
                and merged_groups[-1][0] == 'list'
                and all(not l.strip() or l.startswith((' ', '\t'))
                        for l in group_lines if l.strip())):
            # 这是一个纯缩进文本的 normal 组，前面是 list → 合并到 list
            merged_groups[-1] = ('list',
                                 merged_groups[-1][1] + group_lines)
        else:
            merged_groups.append((group_type, group_lines))

    groups = merged_groups

    # Step 4: 按类型处理各组
    result_lines: list[str] = []

    for group_type, group_lines in groups:
        if group_type == 'code':
            # 代码块：保留内部结构，去掉外层公共缩进；
            # 同时去除围栏行（``` / ~~~），代码内容不做行内变换
            if group_lines:
                indent = _detect_common_indent(group_lines)
                if indent > 0:
                    group_lines = _remove_common_indent(group_lines, indent)
                for gl in group_lines:
                    if _FENCE.match(gl.strip()):
                        continue  # 围栏行：IM 中无意义，去掉
                    result_lines.append(gl)

        elif group_type == 'blank':
            # 空行：最多保留一个
            result_lines.append('')

        elif group_type in ('list', 'heading', 'table', 'quote'):
            # 保留结构，只去公共缩进
            indent = _detect_common_indent(group_lines)
            if indent >= 2:
                processed = _remove_common_indent(group_lines, indent)
            else:
                processed = group_lines

            if group_type == 'table':
                narrative = _table_to_narrative(processed)
                if narrative is None:
                    narrative = _box_table_to_narrative(processed)
                if narrative is not None:
                    rows = narrative
                elif any(_is_box_table_line(p) for p in processed):
                    # Box-drawing 表格但行数不足以转条目（如单行装饰边框）：
                    # 去掉边框行，把数据行的单元格内容提取出来
                    rows = []
                    for p in processed:
                        stripped = p.strip()
                        if not stripped:
                            continue
                        if stripped[0] in _BOX_BORDER_OPEN and stripped[-1] in _BOX_BORDER_CLOSE:
                            continue
                        if stripped[0] in _BOX_DATA_OPEN and stripped[-1] in _BOX_DATA_OPEN:
                            normalized = re.sub(r'[│┃]', '|', stripped)
                            cells = [c.strip() for c in normalized.strip('|').split('|') if c.strip()]
                            if cells:
                                rows.append(' '.join(cells))
                        else:
                            rows.append(p)
                else:
                    rows = processed
                result_lines.extend(_transform_inline(r) for r in rows)
            elif group_type == 'list':
                merged = []
                for pl in processed:
                    if _UNORDERED_LIST.match(pl) or _ORDERED_LIST.match(pl):
                        merged.append(pl)
                    elif pl.strip() and merged:
                        merged[-1] = merged[-1] + ' ' + pl.strip()
                    elif pl.strip():
                        merged.append(pl)
                result_lines.extend(_transform_inline(m) for m in merged)
            elif group_type == 'heading':
                # ## 标题 → 【标题】，再做行内变换
                for pl in processed:
                    line = _transform_heading_line(pl)
                    result_lines.append(_transform_inline(line))
            else:  # quote
                # 嵌套引用：unwrap → merge → rewrap，避免每行各包一对 『 』
                merged_quotes = _merge_nested_quote_group(processed)
                result_lines.extend(_transform_inline(q) for q in merged_quotes)

        elif group_type == 'normal':
            # 普通段落：去公共缩进 + 保守合并硬换行 + 行内标记转换
            non_blank = [l for l in group_lines if l.strip()]
            if non_blank:
                indent = _detect_common_indent(non_blank)
                dedented = _remove_common_indent(non_blank, indent)
                dedented = _remove_continuation_indent(dedented)
                merged = _merge_hard_wraps(dedented)
                result_lines.extend(_transform_inline(m) for m in merged)

    # Step 5: 压缩过多空行（3+ 个压成 2 个）
    output = '\n'.join(result_lines)
    output = _MULTI_BLANK.sub('\n\n', output)

    # Step 6: 去除首尾空行
    output = output.strip()

    return output


# --- 格式特征检测（用于过滤幽灵捕获）---

def has_format_artifacts(text: str) -> bool:
    """判断文本是否包含 Claude Code / 终端格式痕迹。

    如果内容没有格式痕迹，说明不是从 Claude Code 终端复制的
    （可能是语音输入、Cmd+A 全选、或其他应用复制的干净文本），
    不应加入面板列表。

    检测条件（满足任一即可）：
    1. 所有非空行有 ≥ 2 空格公共缩进
    2. 首行无缩进 + 后续行有 ≥ 2 空格缩进（终端硬换行常见模式）
    3. 行首引用装饰（> 、▎ 、| 、｜ 、│ 等）
    4. 行内含 ≥ 3 个连续 box-drawing 字符（表格内容行也能触发）
    5. 含 Claude Code 输出标记（⏺ ⎿）
    6. Trailing spaces（≥ 2 个）或 Tab
    7. 代码块围栏（``` 或 ~~~）
    8. 兜底：≥ 3 行的中文文本（终端复制的典型场景）
    """
    if not text:
        return False

    lines = text.split('\n')
    non_blank = [l for l in lines if l.strip()]

    if len(non_blank) < 1:
        return False

    # 1. 公共缩进 ≥ 2 空格
    min_indent = min(len(l) - len(l.lstrip()) for l in non_blank)
    if min_indent >= 2:
        return True

    # 2. Claude/Ghostty 常见硬换行：首行无缩进，后续行有 2 空格缩进
    if len(non_blank) >= 2:
        first_indent = len(non_blank[0]) - len(non_blank[0].lstrip(' '))
        continuation_indents = [
            len(line) - len(line.lstrip(' ')) for line in non_blank[1:]
        ]
        continuation_count = sum(indent >= 2 for indent in continuation_indents)
        if first_indent == 0 and continuation_count >= 1:
            return True

    # 3. 行首引用装饰（含 box-drawing 竖线 │ U+2502）
    for line in non_blank:
        stripped = line.lstrip()
        if stripped.startswith(('> ', '▎ ', '| ', '｜ ', '│ ', '│', '>')):
            return True

    # 4. 行内含 ≥ 3 个连续 box-drawing 字符（表格的任意一行都能触发）
    if _BOX_DRAWING_RUN.search(text):
        return True

    # 5. Claude Code 输出标记
    if '⏺' in text or '⎿' in text:
        return True

    # 6. Trailing spaces（≥ 2 个）或 Tab
    for line in lines:
        if line.endswith('  ') or line.endswith('\t'):
            return True

    # 7. 代码块围栏
    for line in non_blank:
        if line.strip().startswith(('```', '~~~')):
            return True

    # 8. 兜底：≥ 3 行的中文文本（终端复制典型场景）
    if len(non_blank) >= 3 and _HAS_CJK.search(text):
        return True

    return False
