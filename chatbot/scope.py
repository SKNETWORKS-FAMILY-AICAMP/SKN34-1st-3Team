"""답변 가능 범위(scope) 판별 — 키워드 블랙리스트 없이 데이터 근거 기반."""

from __future__ import annotations

from chatbot.prompts import OUT_OF_SCOPE_MESSAGE

_GREETING_KW = ("안녕", "하이", "hello", "hi", "반가", "처음")


def is_greeting(query: str) -> bool:
    q = query.strip().lower()
    if len(q) <= 12 and any(k in q for k in _GREETING_KW):
        return True
    return q in ("안녕", "안녕하세요", "hi", "hello")


def can_answer(
    *,
    faq_hits: list,
    has_reference: bool,
    intent: str,
    query: str,
    in_diagnose_flow: bool = False,
) -> bool:
    """답변 허용: FAQ hit / 참고자료 존재 / 진단 intent·진행 중 / 인사."""
    if is_greeting(query):
        return True
    if intent == "diagnose" or in_diagnose_flow:
        return True
    if faq_hits:
        return True
    if has_reference:
        return True
    return False


def out_of_scope_message() -> str:
    return OUT_OF_SCOPE_MESSAGE
