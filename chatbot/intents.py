"""의도 분류, 엔티티 추출, [참고 자료] 조립, 답변 오케스트레이터."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from chatbot import llm_client
from chatbot.prompts import WELCOME_MESSAGE, get_system_prompt
from chatbot.retriever import search_faq
from chatbot.scope import can_answer, is_greeting, out_of_scope_message
from news_api import build_news_query

VALID_PERSONAS = frozenset({
    "ESMD", "ESMI", "ESFD", "ESFI", "ELMD", "ELMI", "ELFD", "ELFI",
    "GSMD", "GSMI", "GSFD", "GSFI", "GLMD", "GLMI", "GLFD", "GLFI",
})

_REGION_NAMES = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
]

_CAR_TOPIC_KW = (
    "차", "suv", "ev", "전기", "하이브리드", "세단", "경차", "자동차",
    "현대", "기아", "제네시스", "테슬라", "bmw", "벤츠", "볼보", "아이오닉",
    "쏘렌토", "팰리세이드", "카니발", "ev9", "모델",
)

_NON_CAR_RECOMMEND_KW = ("주식", "etf", "펀드", "코인", "비트코인", "부동산", "맛집", "영화")


@dataclass
class ChatContext:
    faq_df: pd.DataFrame
    cars_df: pd.DataFrame
    region_df: pd.DataFrame
    persona_meta: dict[str, tuple[str, str]]
    recommend_fn: Callable[[str, pd.DataFrame], pd.DataFrame]
    news_fn: Callable[[str, int], list[dict]]
    region_full_map: dict[str, str] = field(default_factory=dict)


def classify_intent(query: str) -> str:
    q = query.lower().strip()
    if is_greeting(query):
        return "greeting"
    if any(k in q for k in ("진단", "테스트", "나의 car", "내 car", "성향 분석")):
        return "diagnose"
    if any(k in q for k in ("뉴스", "기사", "소식", "최신")):
        return "news"
    if any(k in q for k in ("지역", "서울", "부산", "경기", "제주", "시도", "전국")):
        if any(r in query for r in _REGION_NAMES) or "지역" in q:
            return "region"
    if any(k in q for k in ("추천", "어떤 차", "뭐 살", "골라", "맞는 차", "차량 추천")):
        return "recommend"
    if any(k in q for k in ("faq", "질문", "보조금", "유지", "충전", "보험", "할부", "as")):
        return "faq"
    if _extract_persona_code(query):
        return "recommend"
    return "faq"


def _extract_persona_code(query: str) -> str | None:
    m = re.search(r"(?:car[- ]?bti\s*[=:]?\s*)?([eg][ls][fm][id])", query, re.I)
    if m:
        code = m.group(1).upper()
        if code in VALID_PERSONAS:
            return code
    m2 = re.search(r"\b([EG][LS][FM][ID])\b", query)
    if m2 and m2.group(1) in VALID_PERSONAS:
        return m2.group(1)
    return None


def infer_persona_from_query(query: str) -> str | None:
    code = _extract_persona_code(query)
    if code:
        return code

    q = query.lower()
    parts: list[str] = []

    if any(k in q for k in ("전기", "ev", "하이브리드", "친환경", "테슬라", "아이오닉")):
        parts.append("E")
    elif any(k in q for k in ("가솔린", "디젤", "내연", "lpg")):
        parts.append("G")

    if any(k in q for k in ("suv", "대형", "패밀리", "캠핑", "7인승", "미니밴")):
        parts.append("L")
    elif any(k in q for k in ("소형", "세단", "경차", "도심", "컴팩트")):
        parts.append("S")

    if any(k in q for k in ("수입", "bmw", "벤츠", "볼보", "아우디", "테슬라")):
        parts.append("I")
    elif any(k in q for k in ("국산", "현대", "기아", "제네시스", "쌍용")):
        parts.append("D")

    if len(parts) >= 2:
        prefix = "".join(parts[:2])
        matches = [p for p in VALID_PERSONAS if p.startswith(prefix)]
        if len(matches) == 1:
            return matches[0]
        if matches:
            return matches[0]
    return None


def extract_entities(query: str, ctx: ChatContext) -> dict[str, Any]:
    entities: dict[str, Any] = {"regions": [], "brands": [], "models": [], "persona": None}
    entities["persona"] = infer_persona_from_query(query) or _extract_persona_code(query)

    for region in _REGION_NAMES:
        if region in query:
            entities["regions"].append(region)

    if not ctx.cars_df.empty:
        for _, row in ctx.cars_df.iterrows():
            brand = str(row.get("brand", ""))
            model = str(row.get("car_model", ""))
            if brand and brand in query:
                entities["brands"].append(brand)
            if model and model in query:
                entities["models"].append(model)

    return entities


def _is_car_topic(query: str) -> bool:
    q = query.lower()
    if any(k in q for k in _NON_CAR_RECOMMEND_KW):
        return False
    return any(k in q for k in _CAR_TOPIC_KW) or bool(re.search(r"[가-힣]{2,}차", query))


def _should_include_cars(intent: str, query: str, entities: dict) -> bool:
    if intent == "recommend":
        return _is_car_topic(query) or bool(entities.get("persona"))
    if entities.get("persona") or entities.get("brands") or entities.get("models"):
        return _is_car_topic(query)
    return False


def _should_include_region(query: str, entities: dict, intent: str) -> bool:
    return intent == "region" or bool(entities.get("regions"))


def _should_include_news(intent: str, query: str, entities: dict) -> bool:
    if intent == "news":
        return True
    q = query.lower()
    if "뉴스" in q or "기사" in q:
        return True
    return bool(entities.get("brands") or entities.get("models")) and intent in ("recommend", "faq")


def _format_cars_block(cars: pd.DataFrame, persona: str | None) -> str:
    if cars.empty:
        return ""
    lines = [f"### 추천 차량 카탈로그 (페르소나: {persona or '조건 매칭'})"]
    for _, row in cars.head(8).iterrows():
        lines.append(
            f"- {row.get('brand', '')} {row.get('car_model', '')} | "
            f"가격: {row.get('price', '미상')} | 사유: {row.get('reason', '')}"
        )
    return "\n".join(lines)


def _format_faq_block(hits: list[dict]) -> str:
    if not hits:
        return ""
    lines = ["### FAQ"]
    for h in hits:
        lines.append(f"Q ({h.get('company', '')}): {h['question']}")
        lines.append(f"A: {h['answer']}")
    return "\n".join(lines)


def _format_region_block(region_df: pd.DataFrame, regions: list[str], persona_meta: dict) -> str:
    if region_df.empty or not regions:
        return ""
    lines = ["### 지역 Car-BTI"]
    for name in regions[:2]:
        matched = region_df[region_df["region"].str.contains(name, na=False)]
        if matched.empty:
            continue
        row = matched.iloc[0]
        persona = row.get("persona_code", "")
        nick, summary = persona_meta.get(persona, ("", ""))
        lines.append(
            f"- {row.get('region', name)} ({row.get('region_full', name)}): "
            f"코드 {persona} {nick}\n"
            f"  친환경 {row.get('eco_ratio', 0):.1f}% / 대형 {row.get('large_ratio', 0):.1f}% / "
            f"여성 {row.get('female_ratio', 0):.1f}% / 수입 {row.get('import_ratio', 0):.1f}%\n"
            f"  {summary}"
        )
    return "\n".join(lines)


def _format_news_block(articles: list[dict]) -> str:
    if not articles:
        return ""
    lines = ["### 뉴스"]
    for a in articles[:5]:
        lines.append(
            f"- [{a.get('title', '')}]({a.get('link', '')}) "
            f"({a.get('published_at', '')})"
        )
        if a.get("description"):
            lines.append(f"  {a['description'][:120]}")
    return "\n".join(lines)


def _format_persona_meta(persona: str | None, persona_meta: dict) -> str:
    if not persona or persona not in persona_meta:
        return ""
    nick, summary = persona_meta[persona]
    return f"### 페르소나 {persona}\n- {nick}\n- {summary}"


def build_reference_material(
    query: str,
    ctx: ChatContext,
    intent: str,
    faq_hits: list[dict],
) -> str:
    entities = extract_entities(query, ctx)
    blocks: list[str] = []

    persona = entities.get("persona")
    if persona:
        blocks.append(_format_persona_meta(persona, ctx.persona_meta))

    if _should_include_cars(intent, query, entities):
        cars = pd.DataFrame()
        if persona:
            cars = ctx.recommend_fn(persona, ctx.cars_df)
        if cars.empty and (entities.get("brands") or entities.get("models")):
            filt = ctx.cars_df.copy()
            if entities.get("brands"):
                filt = filt[filt["brand"].isin(entities["brands"])]
            if entities.get("models") and not filt.empty:
                filt = filt[filt["car_model"].isin(entities["models"])]
            cars = filt.head(8)
        if not cars.empty:
            blocks.append(_format_cars_block(cars, persona))

    if _should_include_region(query, entities, intent):
        regions = entities.get("regions") or []
        if regions:
            blocks.append(_format_region_block(ctx.region_df, regions, ctx.persona_meta))

    if _should_include_news(intent, query, entities):
        brands = entities.get("brands", [])
        models = entities.get("models", [])
        if not brands and persona:
            rec = ctx.recommend_fn(persona, ctx.cars_df)
            if not rec.empty:
                brands = rec["brand"].dropna().unique().tolist()[:3]
                models = rec["car_model"].dropna().tolist()[:2]
        if intent == "news" and not brands:
            brands = ["자동차"]
        news_query = build_news_query(brands=brands or ["자동차"], car_models=models)
        try:
            articles = ctx.news_fn(news_query, 5)
        except Exception:
            articles = []
        news_block = _format_news_block(articles)
        if news_block:
            blocks.append(news_block)

    faq_block = _format_faq_block(faq_hits)
    if faq_block:
        blocks.append(faq_block)

    return "\n\n".join(b for b in blocks if b.strip())


def _truncate_at_sentence(text: str, max_len: int = 4000) -> str:
    """문장 경계에서 잘라 미완성 문장 노출을 방지."""
    text = text.strip()
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    for sep in (".", "。", "!", "?", "\n\n", "\n"):
        idx = cut.rfind(sep)
        if idx > max_len // 3:
            return cut[: idx + len(sep)].rstrip()
    return cut.rstrip() + "…"


def _build_fallback_answer(
    query: str,
    ctx: ChatContext,
    intent: str,
    faq_hits: list[dict],
) -> str:
    """LLM 미사용·실패 시 완결된 문장으로 구조화된 답변 생성."""
    if faq_hits:
        h = faq_hits[0]
        company = h.get("company", "")
        src = f" (출처: {company})" if company else ""
        return f"**Q.** {h['question']}\n\n{h['answer']}{src}"

    entities = extract_entities(query, ctx)
    sections: list[str] = []

    if intent == "recommend":
        persona = entities.get("persona") or infer_persona_from_query(query)
        if persona:
            nick, summary = ctx.persona_meta.get(persona, ("", ""))
            sections.append(
                f"🎯 **{persona}** ({nick}) 성향에 맞는 차량을 추천드립니다.\n\n"
                f"{summary}"
            )
            cars = ctx.recommend_fn(persona, ctx.cars_df)
            if not cars.empty:
                sections.append("**추천 차량**")
                for _, row in cars.head(4).iterrows():
                    brand = row.get("brand", "")
                    model = row.get("car_model", "")
                    price = row.get("price", "가격 미상")
                    reason = row.get("reason", "")
                    sections.append(
                        f"- **{brand} {model}** — {price}\n"
                        f"  {reason}"
                    )
            else:
                sections.append(
                    "현재 DB에서 해당 페르소나에 매칭된 차량을 찾지 못했습니다. "
                    "다른 조건으로 다시 질문해 주세요."
                )
        else:
            sections.append(
                "조건에 맞는 페르소나를 특정하기 어렵습니다. "
                "예: *가족용 전기 SUV*, *도심용 국산 세단*처럼 구체적으로 말씀해 주세요."
            )

    elif intent == "region":
        regions = entities.get("regions") or []
        if not regions:
            for name in _REGION_NAMES:
                if name in query:
                    regions.append(name)
        for name in regions[:2]:
            matched = ctx.region_df[ctx.region_df["region"].str.contains(name, na=False)]
            if matched.empty:
                continue
            row = matched.iloc[0]
            persona = str(row.get("persona_code", ""))
            nick, summary = ctx.persona_meta.get(persona, ("", ""))
            full = row.get("region_full", name)
            sections.append(
                f"📍 **{full}**의 Car-BTI는 **[{persona}]** ({nick})입니다.\n\n"
                f"**4축 통계**\n"
                f"- ⚡ 친환경: {float(row.get('eco_ratio', 0)):.1f}%\n"
                f"- 🚙 대형: {float(row.get('large_ratio', 0)):.1f}%\n"
                f"- 👩 여성: {float(row.get('female_ratio', 0)):.1f}%\n"
                f"- 🌍 수입: {float(row.get('import_ratio', 0)):.1f}%\n\n"
                f"{summary}"
            )
        if not sections:
            sections.append(
                "지역명을 포함해 질문해 주세요. 예: *서울 지역 Car-BTI 알려줘*"
            )

    elif intent == "news":
        brands = entities.get("brands", [])
        models = entities.get("models", [])
        persona = entities.get("persona")
        if persona and not brands:
            rec = ctx.recommend_fn(persona, ctx.cars_df)
            if not rec.empty:
                brands = rec["brand"].dropna().unique().tolist()[:3]
                models = rec["car_model"].dropna().tolist()[:2]
        news_query = build_news_query(brands=brands or ["자동차"], car_models=models)
        try:
            articles = ctx.news_fn(news_query, 5)
        except Exception:
            articles = []
        if articles:
            sections.append("📰 **최신 자동차 뉴스**")
            for a in articles[:5]:
                title = a.get("title", "")
                link = a.get("link", "")
                date = a.get("published_at", "")
                sections.append(f"- [{title}]({link}) ({date})")
        else:
            sections.append(
                "뉴스를 불러오지 못했습니다. NAVER API 키 설정과 네트워크를 확인해 주세요."
            )

    elif intent == "diagnose":
        sections.append(
            "🧪 Car-BTI 진단을 시작합니다!\n\n"
            "첫 번째 질문입니다. 다음 중 더 끌리는 쪽을 알려주세요.\n"
            "1) ⚡ 전기차·하이브리드 등 친환경 차량\n"
            "2) ⛽ 내연기관(가솔린·디젤·LPG)"
        )

    if sections:
        return "\n\n".join(sections)

    return out_of_scope_message()


def _answer_fallback(
    query: str,
    ctx: ChatContext,
    intent: str,
    faq_hits: list[dict],
    ref: str,
) -> str:
    structured = _build_fallback_answer(query, ctx, intent, faq_hits)
    if structured != out_of_scope_message() or faq_hits:
        return structured
    if ref.strip():
        return _truncate_at_sentence(ref)
    return out_of_scope_message()


def answer(
    query: str,
    ctx: ChatContext,
    history: list[dict[str, str]],
    *,
    in_diagnose_flow: bool = False,
) -> str:
    if is_greeting(query):
        return WELCOME_MESSAGE

    intent = classify_intent(query)
    faq_hits = search_faq(query, ctx.faq_df, top_k=3)
    ref = build_reference_material(query, ctx, intent, faq_hits)

    if not can_answer(
        faq_hits=faq_hits,
        has_reference=bool(ref.strip()),
        intent=intent,
        query=query,
        in_diagnose_flow=in_diagnose_flow,
    ):
        return out_of_scope_message()

    if not llm_client.is_available():
        return _answer_fallback(query, ctx, intent, faq_hits, ref)

    system = get_system_prompt(intent)
    user_content = f"사용자 질문: {query}"
    if ref.strip():
        user_content += f"\n\n[참고 자료]\n{ref}"
    user_content += (
        "\n\n[답변 지침] 모든 문장을 완결된 형태로 끝내세요. "
        "중간에 끊기지 않게 하고, 참고 자료에 있는 정보만 사용하세요."
    )

    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for turn in history[-8:]:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": user_content})

    try:
        reply = llm_client.chat_completion(messages)
        if reply:
            return reply
    except Exception:
        pass
    return _answer_fallback(query, ctx, intent, faq_hits, ref)
