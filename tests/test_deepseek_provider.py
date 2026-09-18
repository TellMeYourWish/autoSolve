import pytest

from autosolve.deepseek_provider import build_prompt, parse_solution
from autosolve.models import NormalizedQuestion


def test_prompt_requires_machine_readable_answer():
    prompt = build_prompt(NormalizedQuestion("1+1=?", 0, ["1", "2"]))
    assert "只返回一个 JSON 对象" in prompt
    assert "多选题使用 # 分隔" in prompt


def test_parse_solution_accepts_json_code_fence():
    result = parse_solution('```json\n{"answer":"2","confidence":0.9,"explanation":"基本算术"}\n```')
    assert result.answer == "2"
    assert result.confidence == 0.9


def test_parse_solution_extracts_json_from_surrounding_text():
    result = parse_solution('答案如下：{"answer":"2","confidence":1,"explanation":"计算结果"}（完）')
    assert result.answer == "2"


def test_parse_solution_rejects_non_json():
    with pytest.raises(ValueError):
        parse_solution("答案是 2")
