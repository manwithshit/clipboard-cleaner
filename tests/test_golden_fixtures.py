"""Golden fixture tests — 读取 tests/fixtures 中的 input/expected 对，
验证清洗结果与期望输出一致。"""

import pathlib
import pytest
from cleaner import clean

FIXTURE_DIR = pathlib.Path(__file__).parent / 'fixtures'


def _get_fixture_pairs():
    pairs = []
    for input_file in sorted(FIXTURE_DIR.glob('*_input.txt')):
        name = input_file.stem.replace('_input', '')
        expected_file = input_file.parent / f'{name}_expected.txt'
        if expected_file.exists():
            pairs.append((input_file.name, input_file, expected_file))
    return pairs


@pytest.mark.parametrize('name,input_path,expected_path', _get_fixture_pairs())
def test_golden_fixture(name, input_path, expected_path):
    raw = input_path.read_text(encoding='utf-8')
    expected = expected_path.read_text(encoding='utf-8').strip()
    result = clean(raw).strip()
    assert result == expected, f'Fixture {name} failed:\nExpected:\n{expected!r}\nGot:\n{result!r}'
