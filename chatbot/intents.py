"""
chatbot/intents.py
==================
사용자 입력을 받아 의도를 파악하고, 필요한 데이터(FAQ·차량·지역·뉴스)를
[참고 자료]로 모아 LLM에게 답변을 생성시키는 핵심 오케스트레이터.

LLM을 쓸 수 없는 환경(키/패키지 없음)에서는 규칙 기반 폴백으로 답한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from . import llm_client, prompts
from .retriever import search_faq

VALID_PERSONAS = {
    "ESMD", "ESMI", "ESFD", "ESFI", "ELMD", "ELMI", "ELFD", "ELFI",
    "GSMD", "GSMI", "GSFD", "GSFI", "GLMD", "GLMI", "GLFD", "GLFI",
}


@dataclass
class ChatContext:
    """app.py가 챗봇에 넘겨주는 데이터/헬퍼 묶음 (순환 import 방지용)."""

    faq_df: pd.DataFrame
    cars_df: pd.DataFrame
    region_df: pd.DataFrame
    persona_meta: dict = field(default_factory=dict)  # {코드: (별명, 요약)}
    recommend_fn: Callable[[str, pd.DataFrame], pd.DataFrame] | None = None
    news_fn: Callable[[list[str], list[str]], list[dict]] | None = None


# ────────────────────────────────────────
# 의도 분류 (가벼운 규칙 기반)
# ────────────────────────────────────────
_RECO_KW = ("추천", "추천해", "골라", "어떤 차", "무슨 차", "살까", "구매", "사고 싶", "예산")
_DIAG_KW = ("진단", "성향", "내 유형", "나의 유형", "car-bti", "carbti", "테스트", "mbti")
_NEWS_KW = ("뉴스", "소식", "기사", "최신")
_REGION_KW = ("지역", "지방", "시도", "서울", "부산", "대구", "인천", "광주", "대전",
              "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남",
              "경북", "경남", "제주")


def classify_intent(query: str) -> str:
    q = query.lower()
    if any(k in q for k in _DIAG_KW):
        return "diagnose"
    if any(k in q for k in _RECO_KW):
        return "recommend"
    if any(k in q for k in _NEWS_KW):
        return "news"
    if any(k in q for k in _REGION_KW):
        return "region"
    return "faq"


def detect_persona(text: str) -> str | None:
    """텍스트에서 유효한 4자리 Car-BTI 코드를 찾는다. (CARBTI=XXXX 우선)"""
    m = re.search(r"CARBTI\s*=\s*([EG][LS][FM][ID])", text, re.IGNORECASE)
    if m:
        code = m.group(1).upper()
        if code in VALID_PERSONAS:
            return code
    for m in re.finditer(r"\b([EG][LS][FM][ID])\b", text.upper()):
        if m.group(1) in VALID_PERSONAS:
            return m.group(1)
    return None


# ────────────────────────────────────────
# [참고 자료] 조립
# ────────────────────────────────────────
def _car_catalog(cars: pd.DataFrame, persona: str | None, limit: int = 24) -> str:
    if cars is None or cars.empty:
        return ""
    df = cars
    code_col = "mbti" if "mbti" in cars.columns else "persona_code"
    if persona and code_col in cars.columns:
        matched = cars[cars[code_col] == persona]
        if not matched.empty:
            df = matched
    df = df.head(limit)
    lines = []
    for _, c in df.iterrows():
        code = c.get(code_col, "")
        price = c.get("price", "")
        reason = str(c.get("reason", "") or "")[:60]
        lines.append(
            f"- [{code}] {c.get('brand', '')} {c.get('car_model', '')}"
            f" / 가격: {price} / 포인트: {reason}"
        )
    return "\n".join(lines)


def _region_summary(region_df: pd.DataFrame) -> str:
    if region_df is None or region_df.empty:
        return ""
    name_col = "region_full" if "region_full" in region_df.columns else "region"
    lines = [
        f"- {r.get(name_col, r.get('region', ''))}: {r.get('persona_code', '')}"
        for _, r in region_df.iterrows()
    ]
    return "\n".join(lines)


def _news_block(ctx: ChatContext, persona: str | None) -> str:
    if ctx.news_fn is None:
        return ""
    brands, models = [], []
    if persona and ctx.recommend_fn is not None:
        rec = ctx.recommend_fn(persona, ctx.cars_df)
        if rec is not None and not rec.empty:
            if "brand" in rec.columns:
                brands = rec["brand"].dropna().astype(str).unique().tolist()
            if "car_model" in rec.columns:
                models = rec["car_model"].dropna().astype(str).head(2).tolist()
    try:
        articles = ctx.news_fn(brands, models)
    except Exception:
        return ""
    if not articles:
        return ""
    return "\n".join(f"- {a.get('title', '')} ({a.get('link', '')})" for a in articles[:5])


# ────────────────────────────────────────
# 답변 생성
# ────────────────────────────────────────
def _history_messages(history: list[dict], limit: int = 8) -> list[dict]:
    msgs = []
    for m in history[-limit:]:
        role = m.get("role")
        if role in ("user", "assistant"):
            msgs.append({"role": role, "content": m.get("content", "")})
    return msgs


def answer(query: str, history: list[dict], ctx: ChatContext) -> str:
    """사용자 질문 → 챗봇 답변 텍스트."""
    intent = classify_intent(query)
    
    # FAQ는 필요한 경우만 검색 (항상 검색 X)
    faq_hits = []
    if intent in ("faq", "diagnose"):
        faq_hits = search_faq(query, ctx.faq_df, top_k=2)

    persona = detect_persona(query)
    if persona is None:
        for m in reversed(history):
            persona = detect_persona(m.get("content", ""))
            if persona:
                break

    car_catalog = None
    region_summary = None
    news_block = None
    
    if intent == "recommend":
        car_catalog = _car_catalog(ctx.cars_df, persona, limit=6)
    elif intent == "diagnose":
        car_catalog = _car_catalog(ctx.cars_df, persona, limit=3)
    elif intent == "region":
        region_summary = _region_summary(ctx.region_df)
    elif intent == "news":
        news_block = _news_block(ctx, persona)

    context_block = prompts.build_context_block(
        faq_hits, car_catalog, region_summary, news_block
    )

    if llm_client.is_available():
        return _answer_with_llm(query, history, intent, context_block)
    return _answer_fallback(query, intent, faq_hits, ctx, persona)


def _answer_with_llm(query: str, history: list[dict], intent: str, context_block: str) -> str:
    system = prompts.SYSTEM_BASE
    if intent == "diagnose":
        system += "\n" + prompts.SYSTEM_DIAGNOSE

    messages: list[dict] = [{"role": "system", "content": system}]
    messages.extend(_history_messages(history))
    user_content = query
    if context_block:
        user_content = f"{context_block}\n\n[사용자 질문]\n{query}"
    messages.append({"role": "user", "content": user_content})

    try:
        return llm_client.chat(messages)
    except Exception as exc:  # API 오류 시에도 앱이 죽지 않도록
        msg = str(exc)
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            return (
                "⏳ 무료 사용량(요청 한도)을 잠시 초과했어요. 1분 정도 뒤에 다시 시도해 주세요.\n"
                "(Gemini 무료 티어는 분당·일일 요청 수 제한이 있습니다.)"
            )
        if "404" in msg and "not found" in msg.lower():
            return (
                "⚠️ 설정된 AI 모델을 찾을 수 없어요. `.env` 의 `GEMINI_CHAT_MODEL` 값을 "
                "`gemini-2.5-flash` 로 확인해 주세요."
            )
        return (
            "⚠️ AI 응답 생성 중 문제가 발생했어요. 잠시 후 다시 시도해 주세요.\n"
            f"(원인: {type(exc).__name__} - {msg[:150]})"
        )


def _answer_fallback(
    query: str, intent: str, faq_hits: list[dict], ctx: ChatContext, persona: str | None
) -> str:
    """LLM 키가 없을 때의 규칙 기반 답변 (앱이 항상 동작하도록)."""
    if intent == "diagnose":
        return (
            "🧪 정확한 Car-BTI 진단은 상단 **'🧪 나의 Car-BTI 테스트'** 탭에서 "
            "4가지 질문에 답해 확인할 수 있어요!\n\n"
            "(AI 대화형 진단을 쓰려면 `GEMINI_API_KEY` 를 설정해 주세요.)"
        )

    if intent == "recommend":
        catalog = _car_catalog(ctx.cars_df, persona, limit=6)
        if catalog:
            head = f"[{persona}] 성향" if persona else "대표"
            return f"🚗 {head} 추천 차량이에요:\n\n{catalog}"
        return "추천할 차량 정보를 찾지 못했어요. 차량 DB가 적재되어 있는지 확인해 주세요."

    if not faq_hits:
        return (
            "🤔 관련 FAQ를 찾지 못했어요. 질문을 조금 더 구체적으로 적어주시겠어요?\n"
            "(더 자연스러운 대화형 답변을 원하시면 `GEMINI_API_KEY` 를 설정해 주세요.)"
        )

    top = faq_hits[0]
    lines = [f"💬 가장 관련 있는 FAQ예요 (출처: {top['company']}):", "", f"**Q. {top['question']}**", top["answer"]]
    if len(faq_hits) > 1:
        lines.append("\n관련 질문도 참고해 보세요:")
        for hit in faq_hits[1:3]:
            lines.append(f"- {hit['question']} (출처: {hit['company']})")
    return "\n".join(lines)
