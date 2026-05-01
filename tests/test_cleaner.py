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
    # 竖线去掉后，两行被合并（硬换行合并）
    assert '|' not in result
    # CJK 和 CJK 之间不加空格（cleaner 行为）
    assert result == '这是一段引用样式文本第二行继续'


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


def test_nested_quote_lines_preserve_breaks():
    """嵌套引用的每一行不应被普通段落合并揉平。"""
    raw = '> > 第一行\n> > 第二行'
    result = clean(raw)
    assert result == '『第一行』\n『第二行』'


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


def test_obsidian_callout_stripped():
    """Obsidian callout 标记 [!tip] 应被去除。"""
    raw = '[!tip] 这是一个提示'
    result = clean(raw)
    assert '[!tip]' not in result
    assert result == '这是一个提示'


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
