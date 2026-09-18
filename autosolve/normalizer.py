from __future__ import annotations

import re
from html import unescape

from .models import NormalizedQuestion, QuestionRequest

QUESTION_TYPES = {
    0: ("单选题", "单项选择题", "单选", "选择题", "single"),
    1: ("多选题", "多项选择题", "多选", "multiple"),
    2: ("填空题", "填空", "completion"),
    3: ("判断题", "是非题", "判断", "judgement", "judgment"),
    4: (
        "简答题", "简答", "问答题", "名词解释", "论述题", "论述", "计算题",
        "计算", "分录题", "资料题", "作图题", "其他", "其它", "阅读理解",
        "阅读", "阅读题", "理解题", "完形填空", "完形", "综合题", "reader",
        "fill", "line", "unknown",
    ),
}


def clean_option(text: str) -> str:
    text = strip_html(text)
    text = re.sub(r"^[A-Z][\s]*[.、．）)\s]+", "", text)
    text = re.sub(r"^\([A-Z]\)[\s]*", "", text)
    text = re.sub(r"^（[A-Z]）[\s]*", "", text)
    text = re.sub(r"^[:\s\-_]+", "", text)
    return text.strip()


def strip_html(text: str) -> str:
    text = re.sub(r"<(?!img\b)[^>]*>", "", text, flags=re.IGNORECASE)
    return unescape(text).replace("\u00a0", " ").strip()


def clean_question(text: str) -> str:
    text = strip_html(text)
    text = re.sub(r"^【.*?】\s*", "", text)
    text = re.sub(r"^\[.*?\]\s*", "", text)
    text = re.sub(r"\s*（\d+\.\d+分）$", "", text)
    text = re.sub(r"^\d+[.、]\s*", "", text)
    return clean_option(text)


def detect_type(value: int | str | None, text: str) -> int | None:
    if isinstance(value, int) and value in QUESTION_TYPES:
        return value
    if isinstance(value, str) and value.isdigit() and int(value) in QUESTION_TYPES:
        return int(value)
    haystack = f"{value or ''} {text}".lower()
    for type_id, names in QUESTION_TYPES.items():
        if any(name.lower() in haystack for name in names):
            return type_id
    return None


def split_answer(answer: str) -> list[str]:
    return [part.strip() for part in re.split(r"#+", answer or "") if part.strip()]


def normalize_request(payload: QuestionRequest) -> NormalizedQuestion:
    question = clean_question(payload.question)
    question_type = detect_type(payload.question_type, payload.question)
    options = [clean_option(option) for option in payload.options if clean_option(option)]
    blank_count = None
    if question_type == 2 and payload.metadata.get("blank_count") is not None:
        blank_count = int(payload.metadata["blank_count"])
    session_id = payload.metadata.get("session_id")
    if session_id is not None:
        session_id = str(session_id).strip() or None
    return NormalizedQuestion(question, question_type, options, blank_count, session_id)
