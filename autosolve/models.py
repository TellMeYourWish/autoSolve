from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class QuestionRequest:
    question: str
    question_type: int | str | None = None
    options: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Solution:
    answer: str
    confidence: float | None = None
    explanation: str | None = None
    raw: Any = None


@dataclass(slots=True)
class NormalizedQuestion:
    question: str
    question_type: int | None
    options: list[str]
    blank_count: int | None = None
    session_id: str | None = None
