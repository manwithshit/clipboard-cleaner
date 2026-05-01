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

# 无序列表前缀（用于 aggressive 模式）
_UNORDERED_PREFIX = re.compile(r'^(\s*)([-*•])\s+')
_ORDERED_PREFIX = re.compile(r'^(\s*)\d+[.、)\]]\s+')

# 连续空行（3+ 个压成 2 个）
_MULTI_BLANK = re.compile(r'\n{3,}')

# 单个字符的行（可能是截断产物，但不合并）
_SINGLE_CHAR_LINE = re.compile(r'^.{0,2}$')

BlockType = Literal['code', 'list', 'heading', 'table', 'quote', 'blank', 'normal']


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
        # 检查是否像表格分隔行 (|---|---|)
        if re.match(r'^[\s\-|:]+$', stripped) and '|' in stripped:
            return 'table'
        return 'table'

    if _UNORDERED_LIST.match(line) or _ORDERED_LIST.match(line):
        return 'list'

    return 'normal'


# 行首装饰：引用竖线 | > ｜ │ ▎（支持多层嵌套）
# ▎ (U+258E LEFT ONE QUARTER BLOCK) 是 Claude Code 的实际引用标记
# 匹配形式：> text, > > text, | | text, ｜ ｜ text, ▎ text, ▎ ▎ text 等
_NESTED_QUOTE = re.compile(r'^(\s*)((?:[│｜|>▎]\s*)+)')

# 单个装饰字符（用于计算嵌套层级）
_SINGLE_DECOR = re.compile(r'[│｜|>▎]\s*')

# Obsidian callout / admonition 标记：[!tip]、[!note]、[!warning] 等
# 终端中无法渲染，清洗时应去掉
_OBSIDIAN_CALLOUT = re.compile(r'^\[![a-zA-Z]+\]\s*')

_CODE_DECOR = re.compile(r'^(\s*)((?:[│｜|>▎] ?)+)(.*)$')


def _strip_decorations(line: str) -> tuple[str, int]:
    """去除行首装饰竖线/大于号，返回 (处理后的行, 嵌套层级)。

    嵌套规则：
      > 文本        → level 1, "文本"
      > > 文本      → level 2, "『文本』"
      > > > 文本    → level 3, "『『文本』』"
      | | 文本      → 同理
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

        # 去掉 Obsidian callout 标记（终端不可见）
        rest = _OBSIDIAN_CALLOUT.sub('', rest)

        if level > 1:
            quotes = '『' * (level - 1)
            rest = quotes + rest + '』' * (level - 1)

        return indent + rest, level

    # 表格行：两端有 | 且中间有 | 分隔符
    if stripped.startswith('|') and stripped.endswith('|') and len(stripped) > 2:
        return line, 0
    if stripped.count('|') >= 2:
        return line, 0

    # 去掉 Obsidian callout 标记（无引用装饰的裸 callout）
    if _OBSIDIAN_CALLOUT.match(stripped):
        return _OBSIDIAN_CALLOUT.sub('', stripped), 0

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


def _table_to_narrative(lines: list[str]) -> list[str] | None:
    """把规整 Markdown 表格转成数字条目列表。"""
    rows = [_split_markdown_table_row(line) for line in lines if line.strip()]
    if any(row is None for row in rows) or len(rows) < 3:
        return None

    parsed_rows = [row for row in rows if row is not None]
    headers = [_normalize_table_cell(cell) for cell in parsed_rows[0]]
    if not _is_markdown_table_separator(parsed_rows[1]):
        return None

    headers = [
        header if header else f'列{i + 1}' for i, header in enumerate(headers)
    ]
    if not headers:
        return None

    result: list[str] = []
    item_index = 1
    for row in parsed_rows[2:]:
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

    # Step 2: 去尾空格（所有行）
    lines = [line.rstrip() for line in lines]

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
        else:
            line, quote_level = _strip_decorations(line)

            # 去掉边框整行
            if _is_border_line(line):
                line = ''

        line_type = _classify_line(line, in_code_block)

        if quote_level > 1 and line_type == 'normal':
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
            # 代码块：保留内部结构，去掉外层公共缩进
            if group_lines:
                # 去掉所有行的公共缩进
                indent = _detect_common_indent(group_lines)
                if indent > 0:
                    group_lines = _remove_common_indent(group_lines, indent)
                for gl in group_lines:
                    result_lines.append(gl)

        elif group_type == 'blank':
            # 空行：最多保留一个
            result_lines.append('')

        elif group_type in ('list', 'heading', 'table', 'quote'):
            # 保留结构，只去公共缩进
            # 但保留列表的缩进层级
            indent = _detect_common_indent(group_lines)
            # 如果是列表/标题/表格，只去掉异常大的公共缩进
            # （Claude Code 经常整体加 2 空格）
            if indent >= 2:
                processed = _remove_common_indent(group_lines, indent)
            else:
                processed = group_lines

            if group_type == 'table':
                narrative = _table_to_narrative(processed)
                result_lines.extend(narrative if narrative is not None else processed)
            # 列表项内部：如果列表项跨多行，保守合并
            elif group_type == 'list':
                merged = []
                for pl in processed:
                    if _UNORDERED_LIST.match(pl) or _ORDERED_LIST.match(pl):
                        merged.append(pl)
                    elif pl.strip() and merged:
                        # 可能是列表项的延续行，合并到上一项
                        merged[-1] = merged[-1] + ' ' + pl.strip()
                    elif pl.strip():
                        merged.append(pl)
                result_lines.extend(merged)
            else:
                result_lines.extend(processed)

        elif group_type == 'normal':
            # 普通段落：去公共缩进 + 保守合并硬换行
            non_blank = [l for l in group_lines if l.strip()]
            if non_blank:
                indent = _detect_common_indent(non_blank)
                dedented = _remove_common_indent(non_blank, indent)
                dedented = _remove_continuation_indent(dedented)
                merged = _merge_hard_wraps(dedented)
                result_lines.extend(merged)
            # 保留组内的空行位置
            for i, l in enumerate(group_lines):
                if not l.strip() and i > 0:
                    # 在组内空行位置插入空行
                    result_lines.append('')

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
    2. 存在行首引用装饰（> 、| 、▎ 等）
    3. 多行以 > 或 ▎ 开头
    4. 存在 ASCII 边框整行
    5. 存在 trailing spaces（≥ 2 个行尾空格）
    6. 存在代码块围栏（``` 或 ~~~）
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

    # 1b. Claude/Ghostty 常见硬换行：首行无缩进，后续行有 2 空格缩进
    # 例如 narrow pane 复制出的回答：
    #   第一行没有缩进
    #     后续视觉续行带两个空格
    if len(non_blank) >= 2:
        first_indent = len(non_blank[0]) - len(non_blank[0].lstrip(' '))
        continuation_indents = [
            len(line) - len(line.lstrip(' ')) for line in non_blank[1:]
        ]
        continuation_count = sum(indent >= 2 for indent in continuation_indents)
        if first_indent == 0 and continuation_count >= 1:
            return True

    # 2. 行首引用装饰
    for line in non_blank:
        stripped = line.lstrip()
        if stripped.startswith(('> ', '▎ ', '| ', '｜ ', '>')):
            return True

    # 3. ASCII 边框整行
    for line in non_blank:
        stripped = line.strip()
        if len(stripped) >= 3 and _IS_BORDER.match(stripped):
            return True

    # 4. Trailing spaces（≥ 2 个）
    for line in lines:
        if line.endswith('  ') or line.endswith('\t'):
            return True

    # 5. 代码块围栏
    for line in non_blank:
        if line.strip().startswith(('```', '~~~')):
            return True

    return False


def clean_aggressive(raw_text: str) -> str:
    """激进清洗模式：额外去掉列表标记，尽量压成连续段落。"""
    result = clean(raw_text)
    lines = result.split('\n')

    new_lines = []
    for line in lines:
        # 去掉无序/有序列表前缀
        line = _UNORDERED_PREFIX.sub(r'\1', line)
        line = _ORDERED_PREFIX.sub(r'\1', line)
        new_lines.append(line)

    # 再去一次硬换行合并
    return '\n'.join(_merge_hard_wraps([l for l in new_lines if l.strip()] or new_lines)).strip()
