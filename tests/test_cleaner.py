"""清洗管线单元测试。

覆盖核心清洗逻辑：换行标准化、缩进、装饰、列表保护、代码块保护、
硬换行合并、空行压缩、边界情况。
"""

import pytest
from cleaner import clean, clean_aggressive


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


# === TC-CLEAN-003：保留 Markdown 无序列表 ===

def test_preserve_unordered_list():
    result = clean('  - 第一步：读取剪贴板\n  - 第二步：清洗文本\n  - 第三步：复制结果')
    assert result == '- 第一步：读取剪贴板\n- 第二步：清洗文本\n- 第三步：复制结果'


# === TC-CLEAN-004：保留有序列表编号 ===

def test_preserve_ordered_list():
    result = clean('  1. 打开 Ghostty\n  2. 运行工具\n  3. 按 0 复制结果')
    assert result == '1. 打开 Ghostty\n2. 运行工具\n3. 按 0 复制结果'


# === TC-CLEAN-005：保护 fenced code block ===

def test_preserve_code_block():
    raw = '  下面是命令：\n\n  ```python\n  def hello():\n      print("hello")\n  ```'
    result = clean(raw)
    assert '```python' in result
    assert 'def hello():' in result
    assert '    print("hello")' in result  # 内部缩进保留
    assert result.endswith('```')
    # 外层公共缩进去掉
    assert '下面是命令：' in result


def test_preserve_code_block_tilde():
    raw = '~~~bash\necho "hello"\n~~~'
    result = clean(raw)
    assert '~~~bash' in result
    assert 'echo "hello"' in result


def test_preserve_code_block_with_indent():
    """代码块内部相对缩进必须保留。"""
    raw = '''```python
def outer():
    def inner():
        pass
    inner()
```'''
    result = clean(raw)
    assert '    def inner():' in result
    assert '        pass' in result


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


def test_heading_preserved():
    result = clean('  ## 标题\n  正文内容')
    assert '## 标题' in result


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
    assert '```python' in result
    assert 'x = 1' in result
    assert '这是介绍：' in result
    assert '这是结尾。' in result


def test_table_preserved():
    """表格不应被破坏。"""
    raw = '| 列 A | 列 B |\n|------|------|\n| 值 1 | 值 2 |'
    result = clean(raw)
    assert '| 列 A | 列 B |' in result


def test_list_item_continuation():
    """列表项跨多行时应合并。"""
    raw = '  - 这是一个很长的列表项，\n    因为终端宽度被折行了'
    result = clean(raw)
    assert '- 这是一个很长的列表项' in result


def test_chinese_english_mixed():
    """中英文混合段落。"""
    result = clean('这是一个 test sentence\nthat wraps here')
    assert '这是一个 test sentence that wraps here' == result


def test_aggressive_removes_list_markers():
    """激进模式去掉列表标记。"""
    result = clean_aggressive('  - 第一步\n  - 第二步\n  - 第三步')
    assert '- ' not in result


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
    assert result == '## 标题\n这是正文内容'


def test_code_block_not_merged():
    """代码块内的换行不能被合并。"""
    raw = '''```python
x = 1
y = 2
```'''
    result = clean(raw)
    assert 'x = 1' in result
    assert 'y = 2' in result


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
