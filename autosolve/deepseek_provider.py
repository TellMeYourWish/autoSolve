from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from .models import NormalizedQuestion, Solution
from .providers import SolverProvider

TYPE_NAMES = {
    0: "单选题",
    1: "多选题",
    2: "填空题",
    3: "判断题",
    4: "简答题",
}


class DeepSeekApiProvider(SolverProvider):
    """通过 DeepSeek 官方 OpenAI 兼容 API 解题。

    仅使用环境变量中的 API key，不读取浏览器 Cookie，也不模拟网页登录。
    """

    def __init__(
        self,
        api_key: str,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = 45,
        retries: int = 2,
    ) -> None:
        if not api_key.strip():
            raise ValueError("DEEPSEEK_API_KEY 不能为空")
        self.api_key = api_key.strip()
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        self.base_url = (base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")).rstrip("/")
        self.timeout = timeout
        self.retries = max(0, retries)

    def solve(self, question: NormalizedQuestion) -> Solution:
        prompt = build_prompt(question)
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                raw = self._chat(prompt, repair=attempt > 0)
                return parse_solution(raw)
            except (ValueError, RuntimeError) as exc:
                last_error = exc
        raise RuntimeError(f"DeepSeek 返回格式无效，重试 {self.retries} 次后仍失败: {last_error}")

    def _chat(self, prompt: str, repair: bool = False) -> str:
        if repair:
            prompt += "\n上一次输出格式不合格。只返回合法 JSON，不要 Markdown 代码块。"
        body = json.dumps({
            "model": self.model,
            "temperature": 0,
            "stream": False,
            "messages": [
                {"role": "system", "content": "你是严谨的学习辅导助手，只返回指定 JSON。"},
                {"role": "user", "content": prompt},
            ],
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"DeepSeek API HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"DeepSeek API 网络错误: {exc}") from exc
        try:
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("DeepSeek API 响应缺少 choices[0].message.content") from exc


def build_prompt(question: NormalizedQuestion) -> str:
    type_name = TYPE_NAMES.get(question.question_type, "未知题型")
    options = "\n".join(f"{index + 1}. {value}" for index, value in enumerate(question.options))
    return (
        "请解答下面的练习题。不要猜测无法判断的内容。\n"
        f"题型：{type_name}\n"
        f"题目：{question.question}\n"
        f"选项：\n{options or '(无选项)'}\n\n"
        "只返回一个 JSON 对象，字段必须是："
        '{"answer":"答案","confidence":0.0,"explanation":"简短理由"}。\n'
        "answer 规则：单选题填写一个完整选项文本；多选题使用 # 分隔多个完整选项文本；"
        "判断题只能填写 对 或 错；填空题按空顺序用 # 分隔；简答题填写简洁答案。"
    )


def parse_solution(raw: str) -> Solution:
    text = raw.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    if not text.startswith("{"):
        match = re.search(r"\{\s*['\"]answer['\"]\s*:", text)
        if match:
            text = text[match.start():]
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        decoder = json.JSONDecoder()
        start = text.find("{")
        if start < 0:
            raise ValueError("模型输出不是合法 JSON") from exc
        try:
            data, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            raise ValueError("模型输出不是合法 JSON") from exc
    if not isinstance(data, dict) or not isinstance(data.get("answer"), str) or not data["answer"].strip():
        raise ValueError("模型 JSON 缺少非空 answer")
    confidence = data.get("confidence")
    if confidence is not None and not isinstance(confidence, (int, float)):
        raise ValueError("confidence 必须是数字")
    return Solution(
        answer=data["answer"].strip(),
        confidence=float(confidence) if confidence is not None else None,
        explanation=data.get("explanation") if isinstance(data.get("explanation"), str) else None,
        raw=data,
    )
