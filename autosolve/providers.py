from __future__ import annotations

from abc import ABC, abstractmethod

from .models import NormalizedQuestion, Solution


class SolverProvider(ABC):
    """解题后端协议；未来可实现 DeepSeek/本地模型 provider。"""

    @abstractmethod
    def solve(self, question: NormalizedQuestion) -> Solution:
        raise NotImplementedError


class NullSolverProvider(SolverProvider):
    """默认 provider，避免服务端偷偷调用外部服务。"""

    def solve(self, question: NormalizedQuestion) -> Solution:
        raise NotImplementedError(
            "未配置解题 provider。请注入 SolverProvider 后再调用 /api/v1/solve。"
        )


class StaticSolverProvider(SolverProvider):
    """开发和联调用 provider，不用于实际解题。"""

    def __init__(self, answer: str = "") -> None:
        self.answer = answer

    def solve(self, question: NormalizedQuestion) -> Solution:
        return Solution(answer=self.answer, confidence=0.0)
