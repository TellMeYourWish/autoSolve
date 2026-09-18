from __future__ import annotations

from .models import QuestionRequest, Solution
from .normalizer import normalize_request
from .providers import SolverProvider


class SolverService:
    def __init__(self, provider: SolverProvider) -> None:
        self.provider = provider

    def solve(self, payload: QuestionRequest) -> tuple[object, Solution]:
        normalized = normalize_request(payload)
        if not normalized.question:
            raise ValueError("question 不能为空")
        return normalized, self.provider.solve(normalized)
