"""
chatbot/scope.py
================
Car-BTI 챗봇 **답변 가능 범위** 판별.

단일 규칙: FAQ·[참고 자료]·진단(intent) 중 하나라도 있으면 답변, 없으면 거절.
(날씨·주식 등 키워드 블랙리스트 없이, 우리 데이터 근거만 본다.)
"""

from __future__ import annotations

_GREETING_KW = ("안녕", "하이", "헬로", "hello", "hi", "반가", "잘 부탁")

# diagnose는 DB·FAQ 없이도 대화형 진단을 시작할 수 있음
_ALWAYS_ALLOWED_INTENTS = frozenset({"diagnose"})


def _normalize(query: str) -> str:
    return (query or "").strip().lower()


def is_greeting(query: str) -> bool:
    q = _normalize(query)
    if not q or len(q) > 30:
        return False
    return any(k in q for k in _GREETING_KW)


def has_usable_context(context_block: str) -> bool:
    return bool(context_block and context_block.strip())


def has_answerable_grounding(
    intent: str,
    faq_hits: list[dict],
    context_block: str,
) -> bool:
    """FAQ·참고 자료·진단 중 하나라도 있으면 답변 가능."""
    if intent in _ALWAYS_ALLOWED_INTENTS:
        return True
    if faq_hits:
        return True
    if has_usable_context(context_block):
        return True
    return False


def should_refuse(
    query: str,
    intent: str,
    faq_hits: list[dict],
    context_block: str,
) -> bool:
    """우리 데이터로 답할 근거가 없으면 True (LLM/API 호출 생략)."""
    if is_greeting(query):
        return False
    return not has_answerable_grounding(intent, faq_hits, context_block)


def needs_out_of_scope_prompt(intent: str, context_block: str) -> bool:
    """참고 자료가 없을 때 LLM에 범위 밖 안내 프롬프트를 추가할지."""
    if has_usable_context(context_block):
        return False
    if intent in _ALWAYS_ALLOWED_INTENTS:
        return False
    return True


def greeting_message() -> str:
    return (
        "안녕하세요! 🚗 **Car-BTI AI 상담 도우미**예요.\n\n"
        "자동차 FAQ, Car-BTI 진단, 차량 추천, 지역 성향, 자동차 뉴스를 도와드릴 수 있어요.\n"
        "궁금한 점을 편하게 물어보세요!"
    )


def out_of_scope_message() -> str:
    return (
        "🚗 저는 **Car-BTI 자동차 상담 도우미**예요.\n"
        "지금 질문에 맞는 **FAQ·차량·지역·뉴스 데이터**를 찾지 못했어요.\n\n"
        "이런 건 물어보실 수 있어요:\n"
        "- 🔧 브랜드/차량 FAQ (예: *전기차 보조금은 어떻게 받나요?*)\n"
        "- 🧪 내 Car-BTI 진단 (예: *내 성향 진단해줘*)\n"
        "- 🚙 차량 추천 (예: *가족용 전기 SUV 추천해줘*)\n"
        "- 📰 자동차 뉴스 · 🗺️ 지역별 Car-BTI"
    )
