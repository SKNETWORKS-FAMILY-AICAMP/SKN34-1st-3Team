"""
chatbot/intents.py
==================
사용자 입력을 받아 의도를 파악하고, 필요한 데이터(FAQ·차량·지역·뉴스)를
[참고 자료]로 모아 LLM에게 답변을 생성시키는 핵심 오케스트레이터.

설계 원칙
---------
- intent는 답변 *스타일*만 결정한다 (거친 분류 4~5종).
- FAQ·차량·지역·뉴스는 질문 엔티티와 키워드에 따라 *병렬*로 조립한다.
- LLM을 쓸 수 없는 환경(키/패키지 없음)에서는 규칙 기반 폴백으로 답한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from . import llm_client, prompts, scope
from .retriever import search_faq

VALID_PERSONAS = {
    "ESMD", "ESMI", "ESFD", "ESFI", "ELMD", "ELMI", "ELFD", "ELFI",
    "GSMD", "GSMI", "GSFD", "GSFI", "GLMD", "GLMI", "GLFD", "GLFI",
}

# 시도명 (region_stats.region 짧은 이름)
_REGION_NAMES = (
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
)
_REGION_FULL_NAMES = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시",
    "인천": "인천광역시", "광주": "광주광역시", "대전": "대전광역시",
    "울산": "울산광역시", "세종": "세종특별자치시", "경기": "경기도",
    "강원": "강원도", "충북": "충청북도", "충남": "충청남도",
    "전북": "전라북도", "전남": "전라남도", "경북": "경상북도",
    "경남": "경상남도", "제주": "제주특별자치도",
}

# ── intent 분류용 (거친 키워드) ──
_STRONG_RECO_KW = ("추천", "추천해", "골라", "어떤 차", "무슨 차", "살까", "구매", "사고 싶", "예산")
_CAR_TOPIC_KW = (
    "suv", "자동차", "차량", "차종", "브랜드", "패밀리", "가족", "가족용",
    "7인", "8인", "전기차", "하이브리드", "친환경", "내연", "세단", "대형", "소형",
)
_CAR_EV_KW = ("전기 ", " ev", "ev ", "ev9", "ev6")  # bare "전기" 단독은 FAQ와 충돌 방지
_FAQ_SIGNAL_KW = (
    "보조금", "방법", "어떻게", "신청", "절차", "as", "서비스", "보증", "충전",
    "왜", "무엇", "뭐야", "알려줘", "설명", "가능", "되나", "문의", "faq",
)
_DIAG_KW = ("진단", "성향", "내 유형", "나의 유형", "car-bti", "carbti", "테스트", "mbti")
_NEWS_KW = ("뉴스", "소식", "기사", "최신", "헤드라인")
_REGION_KW = ("지역", "지방", "시도", "시군") + _REGION_NAMES + tuple(_REGION_FULL_NAMES.values())


@dataclass
class ChatContext:
    """app.py가 챗봇에 넘겨주는 데이터/헬퍼 묶음 (순환 import 방지용)."""

    faq_df: pd.DataFrame
    cars_df: pd.DataFrame
    region_df: pd.DataFrame
    persona_meta: dict = field(default_factory=dict)  # {코드: (별명, 요약)}
    recommend_fn: Callable[[str, pd.DataFrame], pd.DataFrame] | None = None
    news_fn: Callable[[list[str], list[str]], list[dict]] | None = None


@dataclass
class QueryEntities:
    """질문·대화 맥락에서 추출한 검색 단서."""

    persona: str | None = None
    brands: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)  # 짧은 시도명


# ────────────────────────────────────────
# 의도 분류 · 엔티티 추출
# ────────────────────────────────────────
def classify_intent(query: str) -> str:
    """거친 intent — 답변 스타일(프롬프트) 결정용."""
    q = query.lower()

    if any(k in q for k in _NEWS_KW):
        return "news"
    if any(k in query for k in _REGION_NAMES) or any(k in q for k in ("지역", "지방", "시도")):
        return "region"
    if any(k in q for k in _DIAG_KW):
        return "diagnose"
    if _looks_like_faq(query):
        return "faq"
    if any(k in q for k in _STRONG_RECO_KW) or _looks_like_car_topic(query):
        return "recommend"
    return "faq"


def _looks_like_faq(query: str) -> bool:
    q = query.lower()
    if any(k in q for k in _FAQ_SIGNAL_KW):
        return not any(k in q for k in _STRONG_RECO_KW)
    return False


def _looks_like_car_topic(query: str) -> bool:
    q = query.lower()
    if any(k in q for k in _CAR_TOPIC_KW):
        return True
    if any(k in q for k in _CAR_EV_KW):
        return True
    if re.search(r"\b차\b", query):
        return True
    return False


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


def infer_persona_from_query(query: str) -> str | None:
    """자연어 조건(전기 SUV, 가족용 등)에서 Car-BTI 코드 또는 접두(prefix) 추론."""
    q = query.lower()
    if not q.strip():
        return None

    eco = None
    if any(k in q for k in ("전기", "ev", "친환경", "하이브리드", "수소", "전기차")):
        eco = "E"
    elif any(k in q for k in ("내연", "가솔린", "디젤", "휘발유", "lpg")):
        eco = "G"

    size = None
    if any(k in q for k in ("suv", "대형", "가족", "패밀리", "캠핑", "레저", "7인", "8인")):
        size = "L"
    elif any(k in q for k in ("소형", "세단", "경차", "도심", "출퇴근", "주차")):
        size = "S"

    gender = None
    if any(k in q for k in ("여성", "여자", "엄마", "주부")):
        gender = "F"
    elif any(k in q for k in ("남성", "남자", "아빠")):
        gender = "M"

    brand = None
    if any(k in q for k in ("수입", "벤츠", "bmw", "테슬라", "볼보", "아우디", "미니")):
        brand = "I"
    elif any(k in q for k in ("국산", "현대", "기아", "제네시스", "쉐보레")):
        brand = "D"

    parts = [p for p in (eco, size, gender, brand) if p]
    if len(parts) == 4:
        code = "".join(parts)
        return code if code in VALID_PERSONAS else None
    if parts:
        return "".join(parts)
    return None


def extract_entities(query: str, history: list[dict], cars_df: pd.DataFrame) -> QueryEntities:
    """질문 + 최근 대화에서 브랜드·모델·지역·페르소나를 추출."""
    texts = [query]
    for m in reversed(history[-6:]):
        if m.get("role") == "user":
            texts.append(m.get("content", ""))
    combined = " ".join(texts)

    persona = detect_persona(query) or infer_persona_from_query(query)
    if persona is None:
        for t in texts[1:]:
            persona = detect_persona(t) or infer_persona_from_query(t)
            if persona:
                break

    brands: list[str] = []
    models: list[str] = []
    if cars_df is not None and not cars_df.empty:
        q_lower = query.lower()
        for brand in cars_df["brand"].dropna().astype(str).unique():
            if brand and (brand in query or brand.lower() in q_lower):
                brands.append(brand)
        for model in cars_df["car_model"].dropna().astype(str).unique():
            ml = model.lower()
            if model in query or ml in q_lower:
                models.append(model)

    regions: list[str] = []
    for short in _REGION_NAMES:
        full = _REGION_FULL_NAMES.get(short, "")
        if short in query or (full and full in query):
            regions.append(short)

    return QueryEntities(persona=persona, brands=brands, models=models, regions=regions)


def _resolve_persona(entities: QueryEntities) -> str | None:
    p = entities.persona
    if p and len(p) == 4 and p in VALID_PERSONAS:
        return p
    return p  # prefix 허용


# ────────────────────────────────────────
# 병렬 [참고 자료] 조립
# ────────────────────────────────────────
def _should_include_cars(query: str, entities: QueryEntities, intent: str) -> bool:
    if intent == "faq":
        return bool(entities.brands or entities.models)
    if intent == "news":
        return bool(entities.models) or any(k in query.lower() for k in _STRONG_RECO_KW)
    if intent == "diagnose":
        return bool(entities.persona or entities.brands or entities.models)
    if intent == "recommend":
        return (
            bool(entities.brands or entities.models or entities.persona)
            or _looks_like_car_topic(query)
            or infer_persona_from_query(query) is not None
        )
    if entities.brands or entities.models or entities.persona:
        return True
    return _looks_like_car_topic(query)


def _should_include_region(query: str, entities: QueryEntities, intent: str) -> bool:
    if intent == "region":
        return True
    if entities.regions:
        return True
    q = query.lower()
    return any(k in q for k in ("지역", "지방", "시도"))


def _should_include_news(query: str, entities: QueryEntities, intent: str) -> bool:
    if intent == "news":
        return True
    q = query.lower()
    if any(k in q for k in _NEWS_KW):
        return True
    # 브랜드/모델 + 뉴스성 표현
    if (entities.brands or entities.models) and any(
        k in q for k in ("최근", "동향", "이슈", "출시", "발표")
    ):
        return True
    return False


def _car_catalog(
    cars: pd.DataFrame,
    entities: QueryEntities,
    query: str = "",
    limit: int = 12,
) -> str:
    if cars is None or cars.empty:
        return ""
    code_col = "mbti" if "mbti" in cars.columns else "persona_code"
    if code_col not in cars.columns:
        return ""

    df = cars.copy()
    persona = _resolve_persona(entities)
    hint = persona or infer_persona_from_query(query)

    if hint:
        if len(hint) == 4 and hint in VALID_PERSONAS:
            matched = df[df[code_col] == hint]
        else:
            matched = df[df[code_col].astype(str).str.startswith(hint)]
        if not matched.empty:
            df = matched

    if entities.brands and "brand" in df.columns:
        brand_matched = df[df["brand"].astype(str).isin(entities.brands)]
        if not brand_matched.empty:
            df = brand_matched

    if entities.models and "car_model" in df.columns:
        model_lower = [m.lower() for m in entities.models]
        model_matched = df[
            df["car_model"].astype(str).apply(lambda x: x.lower() in model_lower or any(m in x for m in entities.models))
        ]
        if not model_matched.empty:
            df = model_matched

    df = df.head(limit)
    if df.empty:
        return ""

    lines = []
    for _, c in df.iterrows():
        code = c.get(code_col, "")
        price = c.get("price", "")
        reason = str(c.get("reason", "") or "")[:120]
        lines.append(
            f"- [{code}] {c.get('brand', '')} {c.get('car_model', '')}"
            f" / 가격: {price} / 추천 사유: {reason}"
        )
    return "\n".join(lines)


def _region_summary(region_df: pd.DataFrame, regions: list[str] | None = None) -> str:
    if region_df is None or region_df.empty:
        return ""
    name_col = "region_full" if "region_full" in region_df.columns else "region"
    df = region_df
    if regions:
        short_set = set(regions)
        full_set = {_REGION_FULL_NAMES.get(r, r) for r in regions}
        mask = df["region"].astype(str).isin(short_set)
        if name_col in df.columns:
            mask = mask | df[name_col].astype(str).isin(full_set)
        filtered = df[mask]
        if not filtered.empty:
            df = filtered

    lines = []
    for _, r in df.iterrows():
        name = r.get(name_col, r.get("region", ""))
        code = r.get("persona_code", "")
        eco = r.get("eco_ratio", "")
        large = r.get("large_ratio", "")
        extra = ""
        if eco != "" and large != "":
            extra = f" (친환경 {eco}%, 대형 {large}%)"
        lines.append(f"- {name}: Car-BTI {code}{extra}")
    return "\n".join(lines)


def _news_brands_models(
    ctx: ChatContext, entities: QueryEntities, persona: str | None
) -> tuple[list[str], list[str]]:
    brands = list(entities.brands)
    models = list(entities.models)

    if persona and ctx.recommend_fn is not None and (not brands or not models):
        rec = ctx.recommend_fn(persona, ctx.cars_df)
        if rec is not None and not rec.empty:
            if not brands and "brand" in rec.columns:
                brands = rec["brand"].dropna().astype(str).unique().tolist()[:3]
            if not models and "car_model" in rec.columns:
                models = rec["car_model"].dropna().astype(str).head(2).tolist()

    return brands, models


def _news_block(ctx: ChatContext, entities: QueryEntities, persona: str | None) -> str:
    if ctx.news_fn is None:
        return ""
    brands, models = _news_brands_models(ctx, entities, persona)
    try:
        articles = ctx.news_fn(brands, models)
    except Exception:
        return ""
    if not articles:
        return ""
    lines = []
    for a in articles[:5]:
        title = a.get("title", "")
        link = a.get("link", "")
        pub = a.get("published_at", "")
        suffix = f" · {pub}" if pub else ""
        lines.append(f"- {title}{suffix} ({link})")
    return "\n".join(lines)


def assemble_context(
    query: str,
    history: list[dict],
    ctx: ChatContext,
    intent: str,
    faq_hits: list[dict],
) -> tuple[str, QueryEntities]:
    """intent와 무관하게 관련 데이터를 병렬 조립."""
    entities = extract_entities(query, history, ctx.cars_df)
    persona = _resolve_persona(entities)

    car_catalog = None
    if _should_include_cars(query, entities, intent):
        car_catalog = _car_catalog(ctx.cars_df, entities, query=query)

    region_summary = None
    if _should_include_region(query, entities, intent):
        region_summary = _region_summary(ctx.region_df, entities.regions or None)

    news_block = None
    if _should_include_news(query, entities, intent):
        news_block = _news_block(ctx, entities, persona)

    context_block = prompts.build_context_block(
        faq_hits, car_catalog, region_summary, news_block
    )
    return context_block, entities


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
    query = (query or "").strip()
    if not query:
        return scope.greeting_message()

    if scope.is_greeting(query) and len(history) <= 2:
        return scope.greeting_message()

    intent = classify_intent(query)
    faq_hits = search_faq(query, ctx.faq_df, top_k=3)
    context_block, entities = assemble_context(query, history, ctx, intent, faq_hits)

    if scope.should_refuse(query, intent, faq_hits, context_block):
        return scope.out_of_scope_message()

    if llm_client.is_available():
        return _answer_with_llm(
            query, history, intent, context_block, faq_hits, ctx, entities
        )
    return _answer_fallback(query, intent, faq_hits, ctx, entities)


def _answer_with_llm(
    query: str,
    history: list[dict],
    intent: str,
    context_block: str,
    faq_hits: list[dict],
    ctx: ChatContext,
    entities: QueryEntities,
) -> str:
    system = prompts.SYSTEM_BASE
    if intent == "diagnose":
        system += "\n" + prompts.SYSTEM_DIAGNOSE
    elif intent == "recommend":
        system += "\n" + prompts.SYSTEM_RECOMMEND
    elif intent == "news":
        system += "\n" + prompts.SYSTEM_NEWS
    elif intent == "region":
        system += "\n" + prompts.SYSTEM_REGION

    if not scope.has_usable_context(context_block) and scope.needs_out_of_scope_prompt(intent, context_block):
        system += "\n" + prompts.SYSTEM_OUT_OF_SCOPE

    messages: list[dict] = [{"role": "system", "content": system}]
    messages.extend(_history_messages(history))
    user_content = query
    if context_block:
        user_content = f"{context_block}\n\n[사용자 질문]\n{query}"
    messages.append({"role": "user", "content": user_content})

    try:
        return llm_client.chat(messages)
    except llm_client.RateLimitError:
        fallback = _answer_fallback(query, intent, faq_hits, ctx, entities)
        return (
            "⏳ AI 응답 한도에 잠시 걸렸어요. 아래는 **기본 모드**로 정리한 답변이에요.\n"
            "잠시 후 다시 질문하시면 AI 답변을 받을 수 있어요.\n\n"
            f"{fallback}"
        )
    except Exception as exc:
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
    query: str,
    intent: str,
    faq_hits: list[dict],
    ctx: ChatContext,
    entities: QueryEntities,
) -> str:
    """LLM 키가 없을 때의 규칙 기반 답변."""
    if intent == "diagnose":
        return (
            "🧪 정확한 Car-BTI 진단은 상단 **'🧪 나의 Car-BTI 테스트'** 탭에서 "
            "4가지 질문에 답해 확인할 수 있어요!\n\n"
            "(AI 대화형 진단을 쓰려면 `GEMINI_API_KEY` 를 설정해 주세요.)"
        )

    if intent == "news":
        news = _news_block(ctx, entities, _resolve_persona(entities))
        if news:
            return f"📰 관련 최신 뉴스예요:\n\n{news}"
        return "📰 뉴스를 불러오지 못했어요. `NAVER_CLIENT_ID`/`SECRET` 설정을 확인해 주세요."

    if intent == "region":
        region = _region_summary(ctx.region_df, entities.regions or None)
        if region:
            return f"🗺️ 지역별 Car-BTI 요약이에요:\n\n{region}"
        return "지역 데이터를 찾지 못했어요."

    if intent == "recommend" or _should_include_cars(query, entities, intent):
        catalog = _car_catalog(ctx.cars_df, entities, query=query, limit=8)
        if catalog:
            head = f"[{entities.persona}] 성향" if entities.persona else "조건에 맞는"
            return f"🚗 {head} 추천 차량이에요:\n\n{catalog}"
        if intent == "recommend" or _looks_like_car_topic(query):
            return "추천할 차량 정보를 찾지 못했어요. 조건을 조금 바꿔서 다시 물어봐 주세요."

    if not faq_hits:
        if scope.should_refuse(query, intent, faq_hits, ""):
            return scope.out_of_scope_message()
        return (
            "🤔 관련 FAQ를 찾지 못했어요. 자동차·Car-BTI 관련 질문으로 다시 물어봐 주세요."
        )

    top = faq_hits[0]
    lines = [
        f"💬 가장 관련 있는 FAQ예요 (출처: {top['company']}):",
        "",
        f"**Q. {top['question']}**",
        top["answer"],
    ]
    if len(faq_hits) > 1:
        lines.append("\n관련 질문도 참고해 보세요:")
        for hit in faq_hits[1:3]:
            lines.append(f"- {hit['question']} (출처: {hit['company']})")
    return "\n".join(lines)
