"""清洗管线单元测试。

覆盖核心清洗逻辑：换行标准化、缩进、装饰、列表保护、代码块保护、
硬换行合并、空行压缩、边界情况。
"""

import pytest
from cleaner import clean


# === TC-CLEAN-001：统一换行符 ===

def test_normalize_crlf():
    """换行符标准化后，普通行会被合并为一段（硬换行合并）。"""
    result = clean('hello\r\nworld\ragain')
    # \r\n 和 \r 都转为 \n，然后三行被合并
    assert result == 'hello world again'


# === TC-CLEAN-002：去除普通段落公共缩进 ===

def test_remove_common_indent():
    result = clean('  这是一段被 Claude Code\n  复制出来的文本')
    assert result == '这是一段被 Claude Code 复制出来的文本'


def test_detect_claude_continuation_indent_artifact():
    """首行无缩进、后续硬换行带 2 空格缩进也应视为 Claude 痕迹。"""
    from cleaner import has_format_artifacts

    raw = 'Codex 改得不错。5\n  个发现都是真实问题\n  ，修复方案合理'
    assert has_format_artifacts(raw) is True


def test_detect_box_drawing_table():
    """box-drawing 表格（含数据行 │、边框行 ┌ ─ ┘ 等）必须被检测到。"""
    from cleaner import has_format_artifacts

    raw = (
        '┌────────────────────┬────────────────────┐\n'
        '│       武将          │       武力值        │\n'
        '├────────────────────┼────────────────────┤\n'
        '│       关羽          │         97          │\n'
        '└────────────────────┴────────────────────┘'
    )
    assert has_format_artifacts(raw) is True


def test_detect_box_drawing_run_inline():
    """行内含 ≥ 3 个连续 box-drawing 字符也应触发。"""
    from cleaner import has_format_artifacts

    raw = '正文内容里有 ─── 这种分隔线'
    assert has_format_artifacts(raw) is True


def test_detect_claude_code_markers():
    """Claude Code 的 ⏺ ⎿ 输出标记必须被检测到。"""
    from cleaner import has_format_artifacts

    raw = '⏺ 已完成任务\n⎿ 详情见日志'
    assert has_format_artifacts(raw) is True


def test_detect_chinese_multiline_fallback():
    """≥ 3 行中文文本（即使没有缩进或装饰符）也应触发兜底规则。"""
    from cleaner import has_format_artifacts

    raw = '曹操率领八十三万大军南下\n诸葛亮舌战群儒说服东吴抗曹\n周瑜定计火烧赤壁。'
    assert has_format_artifacts(raw) is True


def test_skip_short_clean_text():
    """单行无格式特征的纯英文文本不应触发（避免误捕获语音输入等）。"""
    from cleaner import has_format_artifacts

    raw = 'hello world'
    assert has_format_artifacts(raw) is False


# === Frontmatter 假阳性修复 ===

def test_frontmatter_false_positive_kept_as_content():
    """非 YAML 内容被两个 `---` 包住时，不应整段剥离。"""
    raw = '---\n正文\n---'
    assert clean(raw) == '正文'


def test_frontmatter_false_positive_with_indent():
    """带缩进的 `  ---` 也要正确处理（终端复制场景）。"""
    raw = '  ---\n  正文\n  ---'
    assert clean(raw) == '正文'


def test_frontmatter_false_positive_chinese_paragraph():
    """中文段落被两个 `---` 包住，应保留段落。"""
    raw = '''---
妹诗社雅集，黛玉才情出众。
贾府繁华背后暗藏衰败。
---'''
    result = clean(raw)
    assert '妹诗社雅集' in result
    assert '贾府繁华' in result


def test_frontmatter_real_yaml_still_strips():
    """真正的 YAML frontmatter 仍应被剥离。"""
    raw = '---\ntitle: foo\ndate: 2026-05-05\n---\n正文'
    assert clean(raw) == '正文'


def test_frontmatter_yaml_with_list_value():
    """YAML 含列表值的 frontmatter 仍应被剥离。"""
    raw = '---\ntitle: foo\ntags:\n  - a\n  - b\n---\n正文'
    assert clean(raw) == '正文'


def test_frontmatter_yaml_with_comment():
    """YAML 含注释行的 frontmatter 仍应被剥离。"""
    raw = '---\n# 注释\ntitle: foo\n---\n正文'
    assert clean(raw) == '正文'


def test_frontmatter_mixed_content_not_stripped():
    """如果 `---` 包围的内容混合了 YAML 和散文，不剥离（更安全）。"""
    raw = '---\ntitle: foo\n这是普通段落，不是 YAML\n---\n正文'
    result = clean(raw)
    # 散文内容应保留
    assert '这是普通段落' in result


# === 表格折行预处理修复 ===

def test_wrapped_box_table_single_cell():
    """单单元格表格被折成两行，应正确拼接。"""
    raw = '''┌────
────┐
│ 林黛
玉 │
└────
────┘'''
    result = clean(raw)
    assert result == '林黛玉'


def test_wrapped_box_table_multicol():
    """多列表格被窄终端折行，应识别为表格并转条目。"""
    raw = '''  ┌────────────────────┬────────────
  ────────┐
  │       人物          │       性格
            │
  ├────────────────────┼────────────
  ────────┤
  │       林黛玉        │
  多愁善感      │
  └────────────────────┴────────────
  ────────┘'''
    result = clean(raw)
    assert '1. 人物：林黛玉' in result
    assert '性格：多愁善感' in result


def test_wrapped_box_table_orphan_pipe_continuation():
    """孤立的 │ 续行（如 `   │`）应被并回上一行。"""
    raw = '''│ 人物 │ 性格
            │'''
    # 不应该被识别成引用块
    result = clean(raw)
    assert '〔引〕' not in result


def test_unwrapped_box_table_still_works():
    """完整的、未被折行的 box-drawing 表格仍能正常工作（不破坏旧功能）。"""
    raw = '''┌────────────────────┬────────────────────┐
│       武将          │       武力值        │
├────────────────────┼────────────────────┤
│       关羽          │         97          │
│       张飞          │         94          │
└────────────────────┴────────────────────┘'''
    result = clean(raw)
    assert '1. 武将：关羽' in result
    assert '武力值：97' in result
    assert '2. 武将：张飞' in result


def test_no_table_content_unaffected():
    """没有表格的普通内容不受预处理影响（CJK 硬换行合并保持原行为）。"""
    raw = '这是一段普通文字\n第二行也是普通的'
    assert clean(raw) == '这是一段普通文字第二行也是普通的'


def test_remove_claude_continuation_indent():
    """清洗首行无缩进、后续行带 2 空格的硬换行。"""
    raw = 'Codex 改得不错。5\n  个发现都是真实问题\n  ，修复方案合理'
    result = clean(raw)
    assert result == 'Codex 改得不错。5个发现都是真实问题，修复方案合理'


# === TC-CLEAN-003：保留 Markdown 无序列表 ===

def test_preserve_unordered_list():
    result = clean('  - 第一步：读取剪贴板\n  - 第二步：清洗文本\n  - 第三步：复制结果')
    assert result == '- 第一步：读取剪贴板\n- 第二步：清洗文本\n- 第三步：复制结果'


# === TC-CLEAN-004：保留有序列表编号 ===

def test_preserve_ordered_list():
    result = clean('  1. 打开 Ghostty\n  2. 运行工具\n  3. 按 0 复制结果')
    assert result == '1. 打开 Ghostty\n2. 运行工具\n3. 按 0 复制结果'


# === TC-CLEAN-005：fenced code block 在 IM 模式下去围栏保留内容 ===

def test_strip_code_fence_keep_content():
    """``` 围栏在 IM 模式下要被去掉，但代码内容保留。"""
    raw = '  下面是命令：\n\n  ```python\n  def hello():\n      print("hello")\n  ```'
    result = clean(raw)
    assert '```' not in result
    assert 'def hello():' in result
    assert '    print("hello")' in result  # 内部缩进保留
    assert '下面是命令：' in result


def test_strip_code_fence_tilde():
    raw = '~~~bash\necho "hello"\n~~~'
    result = clean(raw)
    assert '~~~' not in result
    assert 'echo "hello"' in result


def test_preserve_code_block_internal_indent():
    """代码块内部相对缩进必须保留（围栏去掉，缩进留）。"""
    raw = '''```python
def outer():
    def inner():
        pass
    inner()
```'''
    result = clean(raw)
    assert '```' not in result
    assert '    def inner():' in result
    assert '        pass' in result
    assert 'def outer():' in result


def test_code_fence_preserves_inline_markers_inside():
    """代码块内的 *、**、` 等标记不该被行内变换误伤。"""
    raw = '```\nx = a * b\nname = "**not bold**"\n```'
    result = clean(raw)
    assert 'a * b' in result        # 不该变成 a  b
    assert '**not bold**' in result  # 不该变成 【not bold】


# === TC-CLEAN-006：去除行首引用竖线 ===

def test_remove_quote_bar():
    result = clean('| 这是一段引用样式文本\n| 第二行继续')
    # 竖线去掉，加引用层级标记 〔引〕，两行硬换行合并
    assert '|' not in result
    assert result == '〔引〕这是一段引用样式文本第二行继续'


def test_remove_chinese_quote_bar():
    """中文全角竖线。"""
    result = clean('｜ 这是一段引用\n｜ 第二行')
    assert '｜' not in result


# === TC-CLEAN-007：不删除正文中的竖线 ===

def test_preserve_inline_pipe():
    result = clean('字段 A | 字段 B | 字段 C')
    assert result == '字段 A | 字段 B | 字段 C'


# === TC-CLEAN-008：删除 ASCII / box drawing 边框整行 ===

def test_remove_border():
    raw = '┌─────┐\n│ 内容         │\n└─────┘'
    result = clean(raw)
    assert '┌' not in result  # top-left corner gone
    assert '└' not in result  # bottom-left corner gone
    assert '│' not in result  # 单元格竖线也去掉
    assert '内容' in result


# === TC-CLEAN-009：保留真实段落换行 ===

def test_preserve_real_paragraph_break():
    result = clean('这是第一段。\n\n这是第二段。')
    assert result == '这是第一段。\n\n这是第二段。'


def test_preserve_english_paragraph_break():
    result = clean('First paragraph.\n\nSecond paragraph.')
    assert result == 'First paragraph.\n\nSecond paragraph.'


# === TC-CLEAN-010：合并明显硬换行（中文）===

def test_merge_chinese_hard_wrap():
    result = clean('这是一段因为终端宽度太窄而被\n强行折断的中文句子')
    assert result == '这是一段因为终端宽度太窄而被强行折断的中文句子'


# === TC-CLEAN-011：英文硬换行合并时补空格 ===

def test_merge_english_hard_wrap():
    result = clean('This sentence was wrapped by the\nterminal renderer.')
    assert result == 'This sentence was wrapped by the terminal renderer.'


# === TC-CLEAN-012：压缩过多空行 ===

def test_compress_blank_lines():
    result = clean('第一段。\n\n\n\n第二段。')
    assert result == '第一段。\n\n第二段。'


# === 额外边界测试 ===

def test_empty_input():
    assert clean('') == ''
    assert clean('   ') == ''
    assert clean('\n\n\n') == ''


def test_single_line():
    result = clean('hello world')
    assert result == 'hello world'


def test_trailing_spaces_removed():
    result = clean('hello   \nworld   ')
    assert result == 'hello world'  # 尾空格去掉，两行合并


def test_heading_transformed_to_brackets():
    """## 标题 在 IM 模式下转成【标题】。"""
    result = clean('  ## 标题\n  正文内容')
    assert '【标题】' in result
    assert '##' not in result


def test_mixed_content():
    """混合段落、列表、代码块。"""
    raw = '''  这是介绍：

  - 第一点
  - 第二点

  代码如下：

  ```python
  x = 1
  ```

  这是结尾。'''
    result = clean(raw)
    assert '- 第一点' in result
    assert '- 第二点' in result
    assert '```' not in result      # 围栏去掉
    assert 'x = 1' in result
    assert '这是介绍：' in result
    assert '这是结尾。' in result


def test_table_converted_to_narrative_items():
    """Markdown 表格应降维成适合聊天粘贴的语义条目。"""
    raw = '| 列 A | 列 B |\n|------|------|\n| 值 1 | 值 2 |'
    result = clean(raw)
    assert result == '1. 列 A：值 1\n   列 B：值 2'


def test_table_with_uneven_cells_converted_to_narrative_items():
    """列数不齐时，多余单元格合并到最后一列，空单元格跳过。"""
    raw = (
        '| 功能 | 状态 | 说明 |\n'
        '|---|---|---|\n'
        '| 清洗 | 完成 | 支持硬换行 | 额外备注 |\n'
        '| 监听 |  | 支持反馈抑制 |'
    )
    result = clean(raw)
    assert result == (
        '1. 功能：清洗\n'
        '   状态：完成\n'
        '   说明：支持硬换行 额外备注\n\n'
        '2. 功能：监听\n'
        '   说明：支持反馈抑制'
    )


def test_list_item_continuation():
    """列表项跨多行时应合并。"""
    raw = '  - 这是一个很长的列表项，\n    因为终端宽度被折行了'
    result = clean(raw)
    assert '- 这是一个很长的列表项' in result


def test_chinese_english_mixed():
    """中英文混合段落。"""
    result = clean('这是一个 test sentence\nthat wraps here')
    assert '这是一个 test sentence that wraps here' == result


def test_question_mark_preserves_break():
    """问号后的换行应该保留。"""
    result = clean('这个问题怎么解决？\n让我们来看看。')
    assert '这个问题怎么解决？' in result
    assert '让我们来看看。' in result


def test_exclamation_preserves_break():
    """感叹号后的换行应该保留。"""
    result = clean('太好了！\n我们成功了。')
    assert result == '太好了！\n我们成功了。'


def test_colon_preserves_break():
    """冒号后的换行应该保留。"""
    result = clean('结果如下：\n- 第一项\n- 第二项')
    assert '结果如下：' in result


def test_no_merge_into_heading():
    """不应该把内容合并到标题行。"""
    raw = '## 标题\n这是正文内容'
    result = clean(raw)
    assert result == '【标题】\n这是正文内容'


def test_code_block_not_merged():
    """代码块内的换行不能被合并。"""
    raw = '''```python
x = 1
y = 2
```'''
    result = clean(raw)
    assert 'x = 1' in result
    assert 'y = 2' in result


def test_decorated_code_block_strips_decor_and_fence():
    """带引用装饰的代码块：装饰被剥离，围栏被去掉，代码缩进保留。"""
    raw = '| ```python\n| def f():\n|     return 1\n| ```'
    result = clean(raw)
    assert result == 'def f():\n    return 1'


def test_nested_quote_lines_merged_into_one_marker():
    """嵌套引用：连续同层级的行先合并，整段加一次 〔引²〕 标记。"""
    raw = '> > 第一行，\n> > 第二行。'
    result = clean(raw)
    assert result == '〔引²〕第一行，第二行。'


def test_dedup_same_raw_hash():
    """测试：相同原始内容清洗后应该一致。"""
    r1 = clean('  hello  \n  world  ')
    r2 = clean('hello\nworld')
    # 清洗后应该相同
    assert r1 == r2


def test_long_wrapped_english_sentence():
    """模拟 Claude Code 输出的英文长句被多次折断。"""
    raw = (
        "Claude Code is a powerful AI coding assistant that can help you\n"
        "write code, debug issues, and learn new technologies. It integrates\n"
        "seamlessly with your terminal and understands your codebase."
    )
    result = clean(raw)
    expected = (
        "Claude Code is a powerful AI coding assistant that can help you "
        "write code, debug issues, and learn new technologies. It integrates "
        "seamlessly with your terminal and understands your codebase."
    )
    assert result == expected


def test_long_wrapped_chinese_sentence():
    """中文长句被终端折断。"""
    raw = (
        "这是一个非常长的中文句子，因为终端窗口太窄而被分成了"
        "多行显示，但我们希望复制的时候能够恢复成完整的一段文字。"
    )
    # 注意：中文没有换行，直接就是一行
    result = clean(raw)
    assert result == raw


def test_long_wrapped_chinese_with_breaks():
    """中文句子被硬换行折断。"""
    raw = (
        "这是一个非常长的中文句子，因为终端窗口太窄而被分成了\n"
        "多行显示，但我们希望复制的时候能够恢复成完整的一段文字。"
    )
    result = clean(raw)
    expected = (
        "这是一个非常长的中文句子，因为终端窗口太窄而被分成了"
        "多行显示，但我们希望复制的时候能够恢复成完整的一段文字。"
    )
    assert result == expected


def test_obsidian_callout_to_label_heading():
    """Obsidian callout [!tip] 标签 → 【标签】（独立成行的标题）。"""
    raw = '[!tip] 这是一个提示'
    result = clean(raw)
    assert '[!tip]' not in result
    assert result == '【这是一个提示】'


def test_obsidian_callout_with_quote_decor():
    """带引用装饰的 callout 行应同时去掉装饰和标记。"""
    raw = '▎ [!tip] 提示\n▎ 内容'
    result = clean(raw)
    assert '[!tip]' not in result
    assert '提示' in result
    assert '内容' in result


def test_obsidian_various_callouts():
    """多种 callout 类型都应被去除。"""
    raw = '[!warning] 警告\n[!note] 笔记\n[!important] 重要'
    result = clean(raw)
    assert '[!' not in result


# ============================================================
# IM 模式行内标记转换（针对粘贴到微信/飞书等不渲染 Markdown 的目标）
# ============================================================

# --- 反引号 inline code ---

def test_inline_code_to_corner_brackets():
    """`code` → 「code」"""
    result = clean('使用 `useState` hook 来管理状态')
    assert result == '使用 「useState」 hook 来管理状态'


def test_multiple_inline_codes_in_one_line():
    result = clean('比较 `foo` 和 `bar` 的差异')
    assert result == '比较 「foo」 和 「bar」 的差异'


def test_inline_code_with_special_chars():
    """反引号内的 *、** 不应被行内变换误伤。"""
    result = clean('正则是 `\\*\\*([^*]+)\\*\\*` 这样的')
    assert '「\\*\\*([^*]+)\\*\\*」' in result


def test_empty_inline_code_left_alone():
    """空反引号 `` 不变换。"""
    result = clean('字面 `` 反引号')
    assert '`` ' in result or '``' in result  # 不会被错配


# --- 加粗 ---

def test_bold_star_to_brackets():
    """**bold** → 【bold】"""
    result = clean('**注意**：这一步不能省')
    assert result == '【注意】：这一步不能省'


def test_bold_underscore_to_brackets():
    """__bold__ → 【bold】"""
    result = clean('__重要__内容')
    assert '【重要】' in result


def test_bold_inside_sentence():
    result = clean('请按 **数字键** 复制对应条目')
    assert result == '请按 【数字键】 复制对应条目'


def test_multiple_bolds():
    result = clean('**第一** 和 **第二** 都重要')
    assert result == '【第一】 和 【第二】 都重要'


# --- 斜体 ---

def test_italic_star_strips_markers():
    """*italic* → italic（去星号留文字）"""
    result = clean('这是 *斜体* 文字')
    assert result == '这是 斜体 文字'


def test_italic_underscore_strips_markers():
    result = clean('这是 _斜体_ 文字')
    assert result == '这是 斜体 文字'


def test_bold_then_italic_in_same_sentence():
    """**粗** 和 *斜* 同时出现，互不干扰。"""
    result = clean('**粗体** 与 *斜体* 共存')
    assert result == '【粗体】 与 斜体 共存'


def test_lone_asterisk_not_treated_as_italic():
    """孤立的 * 不被识别为斜体起止。"""
    result = clean('a * b * c 是数学表达式')
    assert '【' not in result
    # 行内变换不该吃掉这些星号
    assert '*' in result


def test_asterisk_as_bullet_not_treated_as_italic():
    """列表项的 * 是 bullet 标记，不该被行内变换吃。"""
    raw = '* 第一项\n* 第二项'
    result = clean(raw)
    # 列表 marker 必须保留
    assert '*' not in result or result.startswith('* ') or '\n* ' in result
    # 至少不能变成 【】
    assert '【' not in result


# --- 链接 ---

def test_link_to_text_with_url_in_parens():
    """[文字](url) → 文字 (url)"""
    result = clean('参考 [官方文档](https://example.com/docs) 了解详情')
    assert result == '参考 官方文档 (https://example.com/docs) 了解详情'


def test_link_with_chinese_text():
    result = clean('点击 [这里](https://x.com) 跳转')
    assert '这里 (https://x.com)' in result
    assert '[' not in result
    assert ']' not in result


def test_multiple_links_in_one_line():
    result = clean('看 [A](http://a.com) 和 [B](http://b.com)')
    assert 'A (http://a.com)' in result
    assert 'B (http://b.com)' in result


# --- 标题 ---

def test_h1_to_brackets():
    result = clean('# 一级标题')
    assert result == '【一级标题】'


def test_h2_to_brackets():
    result = clean('## 二级标题')
    assert result == '【二级标题】'


def test_h3_to_brackets():
    result = clean('### 三级标题')
    assert result == '【三级标题】'


def test_heading_with_inline_bold():
    """标题里有 **bold**，bold 也要被处理。"""
    result = clean('## 这是 **重点** 标题')
    assert result == '【这是 【重点】 标题】'


def test_heading_with_trailing_hashes():
    """ATX 风格闭合 hash `## 标题 ##` 正确处理。"""
    result = clean('## 标题 ##')
    assert result == '【标题】'


# --- 代码围栏 ---

def test_code_fence_with_language_stripped():
    """围栏行（含语言标识）整行去除，代码内容保留。"""
    raw = '```javascript\nconst x = 1;\n```'
    result = clean(raw)
    assert '```' not in result
    assert 'javascript' not in result
    assert result == 'const x = 1;'


def test_inline_markers_in_normal_paragraph_combined():
    """同一段中混合多种行内标记。"""
    raw = '使用 `npm install` 安装 **依赖**，参考 [官方文档](https://npmjs.com)'
    result = clean(raw)
    assert result == '使用 「npm install」 安装 【依赖】，参考 官方文档 (https://npmjs.com)'


# --- 代码块内的标记不受影响（行内变换隔离） ---

def test_code_block_content_not_inline_transformed():
    """代码块内的 markdown 标记字面保留。"""
    raw = '```\n* item in code\n**not bold**\n[link](url) literal\n```'
    result = clean(raw)
    assert '* item in code' in result
    assert '**not bold**' in result
    assert '[link](url) literal' in result


# --- 列表中的行内标记 ---

def test_inline_transforms_apply_within_list_items():
    """列表项的内容也要做行内变换。"""
    raw = '- 使用 `git` 提交\n- 按 **Esc** 退出'
    result = clean(raw)
    assert '「git」' in result
    assert '【Esc】' in result


# ============================================================
# Bug 1: Callout 标签独立成行
# ============================================================

def test_callout_with_label_and_following_content():
    """[!tip] 小贴士 + 内容行 → 标签独立成 【】，内容独立段落。"""
    raw = '> [!tip] 小贴士\n> 使用 `clean()` 前先备份'
    result = clean(raw)
    lines = result.split('\n')
    assert '【小贴士】' in lines
    # 确保标签和内容不被压在一起
    assert not any(line == '小贴士使用 「clean()」 前先备份' for line in lines)
    # 内容应该出现在另一行
    assert any('「clean()」' in line and '小贴士' not in line for line in lines)


def test_callout_warning_to_label():
    raw = '[!warning] 危险操作'
    result = clean(raw)
    assert result == '【危险操作】'


def test_callout_without_label_disappears():
    """[!info] 后面没有标签文字 → 整行消失。"""
    raw = '[!info]\n正文内容'
    result = clean(raw)
    assert '[!info]' not in result
    assert result == '正文内容'


def test_callout_inline_inside_label():
    """callout 标签里的 ` 也走行内变换。"""
    raw = '[!tip] 使用 `git` 命令'
    result = clean(raw)
    assert result == '【使用 「git」 命令】'


# ============================================================
# Bug 2: CJK 末尾 + 英文大写专有名词合并
# ============================================================

def test_cjk_suffix_then_uppercase_merges():
    """中文末尾无终止标点 + 下一行英文大写专有名词 → 合并。"""
    result = clean('详见这个\nGitHub Issue。')
    assert result == '详见这个 GitHub Issue。'


def test_cjk_suffix_then_uppercase_api():
    result = clean('请调用我们的\nAPI 接口')
    assert result == '请调用我们的 API 接口'


def test_cjk_with_terminator_still_breaks_before_uppercase():
    """中文末尾有句号时，下一行大写仍保留换行。"""
    result = clean('这是一段。\nGitHub is great.')
    assert result == '这是一段。\nGitHub is great.'


def test_english_uppercase_break_still_preserved():
    """纯英文场景，大写规则仍然生效（防止 CJK fix 过度）。"""
    result = clean('end of sentence\nNew sentence starts')
    # 没有终止标点但下一行大写 → 仍保留（英文场景）
    assert result == 'end of sentence\nNew sentence starts'


# ============================================================
# UX A: front-matter 兜底
# ============================================================

def test_standard_yaml_frontmatter_stripped():
    raw = '---\ntitle: foo\ndate: 2026-05-01\n---\n正文内容'
    result = clean(raw)
    assert 'title' not in result
    assert 'date' not in result
    assert result == '正文内容'


def test_pseudo_frontmatter_stripped():
    """GPT 偶尔写 ---  title: "..." 同行的伪 front-matter 也要消除。"""
    raw = '---  title: "示例"\n    date: 2026-05-01\n    tags: [a, b]\n\n正文'
    result = clean(raw)
    assert 'title' not in result
    assert 'date' not in result
    assert 'tags' not in result
    assert result == '正文'


def test_frontmatter_only_stripped_at_start():
    """文档中间的 --- key: value 不能被误识别为 front-matter。"""
    raw = '正文开始\n\n--- some text key: value\n后续内容'
    result = clean(raw)
    # 中间的 `---` 整行作为 border 处理（去掉）
    # 但 `key: value` 不会被当成 front-matter 整段消除
    assert '正文开始' in result


def test_frontmatter_unclosed_kept():
    """开头是 --- 但找不到收尾 ---，保留原样不强删。"""
    raw = '---\nincomplete\nstill incomplete'
    result = clean(raw)
    # 没有收尾 ---，保持
    assert 'incomplete' in result


# ============================================================
# UX B: 嵌套引用合并跨行
# ============================================================

def test_nested_quote_two_levels_marker():
    raw = '> > 第一行，\n> > 第二行。'
    result = clean(raw)
    assert result == '〔引²〕第一行，第二行。'


def test_nested_quote_three_levels_marker():
    raw = '> > > 三层第一行，\n> > > 三层第二行。'
    result = clean(raw)
    assert result == '〔引³〕三层第一行，三层第二行。'


def test_nested_quote_four_levels_marker():
    """4 层及以上同样能用上标数字表达。"""
    raw = '> > > > 第一，\n> > > > 第二。'
    result = clean(raw)
    assert result == '〔引⁴〕第一，第二。'


def test_nested_quote_with_terminator_keeps_break():
    """嵌套引用内有强终止标点的换行仍保留（合并规则一致），每行各自带标记。"""
    raw = '> > 第一句。\n> > 第二句。'
    result = clean(raw)
    assert '〔引²〕第一句。' in result
    assert '〔引²〕第二句。' in result


def test_single_quote_with_marker():
    """单层引用现在也加 〔引〕 标记，跨行仍合并。"""
    raw = '> 第一行，\n> 第二行。'
    result = clean(raw)
    assert result == '〔引〕第一行，第二行。'


# ============================================================
# 新增: ASCII / box-drawing 表格转数字条目
# ============================================================

def test_box_drawing_table_to_narrative():
    raw = '''┌───────┬───────┬───────┐
│ 类别  │ 数量  │ 总和  │
├───────┼───────┼───────┤
│ 源码  │ 5     │ ~960  │
├───────┼───────┼───────┤
│ 文档  │ 2     │ ~490  │
└───────┴───────┴───────┘'''
    result = clean(raw)
    assert '1. 类别：源码' in result
    assert '   数量：5' in result
    assert '   总和：~960' in result
    assert '2. 类别：文档' in result
    assert '┌' not in result
    assert '│' not in result
    assert '├' not in result
    assert '└' not in result


def test_box_drawing_table_with_indent():
    """带 2 空格公共缩进的 box 表格也能正确解析。"""
    raw = '''  ┌───────┬───────┐
  │ K     │ V     │
  ├───────┼───────┤
  │ a     │ 1     │
  ├───────┼───────┤
  │ b     │ 2     │
  └───────┴───────┘'''
    result = clean(raw)
    assert '1. K：a' in result
    assert '2. K：b' in result


def test_box_drawing_single_data_row_fallback():
    """只有一行数据的装饰性 box：边框去掉，内容平铺保留。"""
    raw = '┌─────────┐\n│ 仅一行  │\n└─────────┘'
    result = clean(raw)
    assert '仅一行' in result
    assert '┌' not in result
    assert '│' not in result


def test_box_drawing_with_chinese_content():
    """CJK 列宽对齐空格在解析时被正确去除。"""
    raw = '''┌───────────────┬────────┐
│     类别      │ 数量   │
├───────────────┼────────┤
│ 中文条目1     │ 100    │
├───────────────┼────────┤
│ 中文条目2     │ 200    │
└───────────────┴────────┘'''
    result = clean(raw)
    assert '类别：中文条目1' in result
    assert '数量：100' in result


def test_markdown_table_still_works():
    """改动不能破坏 Markdown 表格的处理。"""
    raw = '| 列 A | 列 B |\n|------|------|\n| 值 1 | 值 2 |'
    result = clean(raw)
    assert result == '1. 列 A：值 1\n   列 B：值 2'


# ============================================================
# Claude Code 前缀标记 ⏺ ⎿ 剥离 + 紧贴的伪 front-matter
# ============================================================

def test_cc_bullet_prefix_stripped():
    """Claude Code 输出气泡 bullet ⏺ 被剥掉。"""
    result = clean('⏺ 这是一段输出')
    assert '⏺' not in result
    assert result == '这是一段输出'


def test_cc_continuation_prefix_stripped():
    """Claude Code 续行 marker ⎿ 也被剥掉。"""
    result = clean('⎿ 这是续行内容')
    assert '⎿' not in result
    assert result == '这是续行内容'


def test_pseudo_frontmatter_no_space_after_dashes():
    """`---title:`（没有空格）也应识别为伪 front-matter。"""
    raw = '---title: 文档\n  date: 2026-05-01\n\n正文'
    result = clean(raw)
    assert 'title' not in result
    assert 'date' not in result
    assert result == '正文'


def test_cc_prefix_plus_pseudo_frontmatter():
    """实战组合：⏺ 前缀 + 紧贴的 ---title: 伪 front-matter 整体剥除。"""
    raw = '⏺ ---title: 测试\n  date: 2026-05-01\n\n正文内容'
    result = clean(raw)
    assert '⏺' not in result
    assert 'title' not in result
    assert 'date' not in result
    assert result == '正文内容'


def test_pseudo_frontmatter_with_leading_whitespace():
    """实战发现：行首带空格的 front-matter（` ---title: ...`）也要兜底剥除。"""
    raw = ' ---title: 文档\n  date: 2026-05-01\n\n正文'
    result = clean(raw)
    assert 'title' not in result
    assert 'date' not in result
    assert result == '正文'


def test_standard_frontmatter_with_leading_whitespace():
    """标准 front-matter 第一行 `---` 也允许有行首空格。"""
    raw = '  ---\n  title: foo\n  ---\n正文'
    result = clean(raw)
    assert 'title' not in result
    assert result == '正文'


def test_quote_preserves_inner_indent():
    """实战发现：单层引用里的代码缩进不能被吃掉。"""
    raw = '▎ def strategy():\n▎     return "空城计"'
    result = clean(raw)
    lines = result.split('\n')
    assert lines[0] == '〔引〕def strategy():'
    # 第二行的 4 空格代码缩进必须保留
    assert lines[1] == '〔引〕    return "空城计"'


def test_quote_preserves_inner_indent_nested():
    """嵌套引用里的内容缩进同样不能被装饰正则吃掉。"""
    raw = '> >     有 4 空格缩进的内容'
    result = clean(raw)
    # 应该是 〔引²〕    有 4 空格缩进的内容
    assert result == '〔引²〕    有 4 空格缩进的内容'
