from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd
from sqlalchemy import text

from chatbot import llm_client
from chatbot.prompts import WELCOME_MESSAGE, get_system_prompt
from chatbot.query_intent import (
    asks_car_recommendation,
    asks_persona_detail,
    asks_persona_region_list,
    asks_region_car_bti,
    asks_same_persona_as_region,
)
from chatbot.retriever import is_stats_query, search_faq, should_try_faq
from chatbot.scope import can_answer, intent_hints, is_greeting, out_of_scope_message
from chatbot.vector_store import VectorIndex
from db_config import get_engine

logger = logging.getLogger(__name__)

# MySQL 8.x 에서 year_month 는 예약어 → 반드시 백틱 필요
_YM = "`year_month`"

PERSONA_RE = re.compile(r"(?<![A-Za-z])([EG][LS][FM][ID])(?![A-Za-z])", re.IGNORECASE)
MONTH_HYPHEN_RE = re.compile(r"\b(20\d{2})-(0[1-9]|1[0-2])\b")
MONTH_PLAIN_RE = re.compile(r"\b(20\d{2})(0[1-9]|1[0-2])\b")

REGION_ALIASES = {
    "서울특별시": "서울",
    "부산광역시": "부산",
    "대구광역시": "대구",
    "인천광역시": "인천",
    "광주광역시": "광주",
    "대전광역시": "대전",
    "울산광역시": "울산",
    "세종특별자치시": "세종",
    "경기도": "경기",
    "강원도": "강원",
    "충청북도": "충북",
    "충청남도": "충남",
    "전라북도": "전북",
    "전라남도": "전남",
    "경상북도": "경북",
    "경상남도": "경남",
    "제주특별자치도": "제주",
}

KNOWN_REGIONS = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
]

ERD_TABLES = [
    {
        "table": "tbl_fuel",
        "dim_col": "fuel",
        "label": "연료",
        "keywords": ["연료", "전기차", "가솔린", "디젤", "하이브리드", "lpg", "내연기관"],
        "value_map": {"전기차": "전기", "내연기관": "가솔린", "가솔린": "가솔린", "디젤": "디젤", "하이브리드": "하이브리드", "lpg": "lpg"},
    },
    {
        "table": "tbl_size",
        "dim_col": "car_size",
        "label": "차량 크기",
        "keywords": ["차크기", "차급", "크기", "대형", "중형", "소형", "suv", "세단"],
        "value_map": {"대형": "대형", "중형": "중형", "소형": "소형", "suv": "suv", "세단": "세단"},
    },
    {
        "table": "tbl_genderage",
        "dim_col": "gender",
        "label": "성별",
        "keywords": ["성별", "남성", "여성", "남자", "여자"],
        "value_map": {"남성": "남", "남자": "남", "여성": "여", "여자": "여"},
    },
    {
        "table": "tbl_import",
        "dim_col": "origin_type",
        "label": "원산 구분",
        "keywords": ["수입", "국산", "원산"],
        "value_map": {"수입": "수입", "국산": "국산"},
    },
    {
        "table": "tbl_total",
        "dim_col": "car_type",
        "label": "차종",
        "keywords": ["차종", "전체", "총등록", "총 등록"],
        "value_map": {},
    },
]


@dataclass
class ChatContext:
    faq_df: pd.DataFrame
    cars_df: pd.DataFrame
    region_df: pd.DataFrame
    persona_meta: dict[str, tuple[str, str]]
    recommend_fn: Callable[[str, pd.DataFrame], pd.DataFrame]
    news_fn: Callable[[list[str], list[str]], list[dict[str, Any]]]
    vector_index: VectorIndex | None = None


def classify_intent(query: str, _: ChatContext) -> str:
    if is_greeting(query):
        return "greeting"

    hints = intent_hints(query)
    if "faq" in hints or should_try_faq(query):
        return "faq"
    if "region_persona" in hints:
        return "region_persona"
    if "car_recommend" in hints:
        return "car_recommend"
    if hints:
        return "db_related"

    if can_answer(query):
        return "db_related"

    llm_related = llm_client.classify_db_related(query)
    if llm_related is True:
        return "db_related"
    return "out_of_scope"


def answer(query: str, ctx: ChatContext) -> str:
    intent = classify_intent(query, ctx)
    if intent == "greeting":
        return WELCOME_MESSAGE
    if intent == "out_of_scope":
        return out_of_scope_message()

    entity = extract_entities(query, ctx)
    try:
        structured = _run_structured_handlers(query, entity, ctx)
        if structured:
            return structured

        context_text = _build_context(query, entity, ctx)
        if not context_text.strip():
            return "조회된 데이터가 없습니다."

        try:
            return llm_client.generate_answer(
                system_prompt=get_system_prompt(),
                user_question=query,
                context_text=context_text,
            )
        except Exception as exc:
            logger.warning("LLM 생성 실패, DB 폴백 사용: %s", type(exc).__name__)
            return _fallback_answer(query, context_text)
    except Exception as exc:
        logger.exception("챗봇 응답 실패: %s", type(exc).__name__)
        return "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요."


def extract_entities(query: str, ctx: ChatContext) -> dict[str, Any]:
    regions = list(KNOWN_REGIONS)
    if not ctx.region_df.empty and "region" in ctx.region_df.columns:
        regions = ctx.region_df["region"].dropna().astype(str).unique().tolist()

    region = _extract_region(query, regions)
    month = _extract_month(query)
    persona = _extract_persona(query, ctx)
    top_n = _extract_top_n(query)
    return {"region": region, "year_month": month, "persona": persona, "top_n": top_n}


def _extract_region(query: str, regions: list[str]) -> str | None:
    # 긴 지역명부터 매칭 (경상남도 vs 경남 등 혼동 방지)
    for region in sorted(regions, key=len, reverse=True):
        if region in query:
            return region
    for long_name, short_name in REGION_ALIASES.items():
        if long_name in query:
            return short_name
    return None


def _extract_month(query: str) -> str | None:
    m1 = MONTH_HYPHEN_RE.search(query)
    if m1:
        return f"{m1.group(1)}-{m1.group(2)}"
    m2 = MONTH_PLAIN_RE.search(query)
    if m2:
        return f"{m2.group(1)}-{m2.group(2)}"
    return None


def _extract_persona(query: str, ctx: ChatContext) -> str | None:
    m = PERSONA_RE.search(query)
    if m:
        return m.group(1).upper()
    q_upper = query.upper()
    for code in ctx.persona_meta.keys():
        if code in q_upper:
            return code
    return None


def _extract_top_n(query: str) -> int:
    m = re.search(r"(top|상위)\s*(\d+)", query.lower())
    if not m:
        return 5
    return max(1, min(int(m.group(2)), 20))


def _run_structured_handlers(query: str, entity: dict[str, Any], ctx: ChatContext) -> str | None:
    handlers = [
        _handle_faq_direct,
        _handle_same_persona_regions,
        _handle_region_persona,
        _handle_persona_regions,
        _handle_metric_top_regions,
        _handle_erd_aggregate,
        _handle_car_recommendation,
        _handle_persona_detail,
    ]
    for handler in handlers:
        result = handler(query, entity, ctx)
        if result:
            return result
    return None


def _handle_faq_direct(query: str, _: dict[str, Any], ctx: ChatContext) -> str | None:
    if not should_try_faq(query) and "faq" not in intent_hints(query):
        return None
    rows = search_faq(ctx.faq_df, query, top_k=3, vector_index=ctx.vector_index)
    if not rows:
        return "질문과 일치하는 FAQ를 찾지 못했습니다. 브랜드명과 주제를 함께 입력해 주세요."
    lines = []
    for idx, row in enumerate(rows, start=1):
        lines.append(
            f"{idx}) [{row.get('company','')}] Q: {row.get('question','')}\n"
            f"   A: {row.get('answer','')}"
        )
    return "요청하신 FAQ입니다.\n" + "\n".join(lines)


def _handle_persona_detail(query: str, entity: dict[str, Any], ctx: ChatContext) -> str | None:
    if asks_persona_region_list(query):
        return None
    if not asks_persona_detail(query):
        return None

    persona = entity.get("persona")
    if not persona and ctx.vector_index and ctx.vector_index.is_ready():
        hits = ctx.vector_index.search_persona(query, top_k=1)
        if hits and float(hits[0].get("_semantic_score", 0)) >= 0.45:
            persona = hits[0].get("persona_code")
    if not persona:
        return None
    try:
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT persona_code, persona_name, persona_keyword, persona_desc "
                    "FROM tbl_persona_detail WHERE persona_code = :code LIMIT 1"
                ),
                {"code": persona},
            ).mappings().first()
            if not row:
                return f"{persona} 유형 상세 정보를 찾지 못했습니다."
            return (
                f"{row['persona_code']} ({row.get('persona_name','')})\n"
                f"- 키워드: {row.get('persona_keyword','')}\n"
                f"- 설명: {row.get('persona_desc','')}"
            )
    except Exception as exc:
        logger.warning("페르소나 상세 조회 실패: %s", type(exc).__name__)
        return None


def _handle_same_persona_regions(query: str, entity: dict[str, Any], ctx: ChatContext) -> str | None:
    if not asks_same_persona_as_region(query, bool(entity.get("region"))):
        return None
    db_result = _query_same_persona_regions_from_db(entity)
    if db_result:
        return db_result
    return _query_same_persona_regions_from_df(entity, ctx.region_df)


def _handle_region_persona(query: str, entity: dict[str, Any], _: ChatContext) -> str | None:
    if not asks_region_car_bti(query, bool(entity.get("region"))):
        return None
    return _query_region_persona_from_db(entity)


def _handle_persona_regions(query: str, entity: dict[str, Any], _: ChatContext) -> str | None:
    persona = entity.get("persona")
    if not persona:
        return None
    if asks_persona_detail(query) and not asks_persona_region_list(query):
        return None
    if asks_persona_region_list(query):
        return _query_persona_regions_from_db(entity, query)
    q = query.lower()
    if ("car-bti" in q or "car bti" in q) and re.search(r"\b[eg][ls][fm][id]\b", q, re.I):
        return _query_persona_regions_from_db(entity, query)
    return None


def _handle_metric_top_regions(query: str, entity: dict[str, Any], _: ChatContext) -> str | None:
    metric_col = _extract_region_stats_metric(query)
    if not metric_col:
        return None
    q = query.lower()
    if not any(k in q for k in ["top", "상위", "가장 높은", "많은 지역", "높은 지역"]):
        return None
    return _query_top_regions_from_region_stats(metric_col, entity)


def _handle_erd_aggregate(query: str, entity: dict[str, Any], _: ChatContext) -> str | None:
    cfg = _detect_erd_table(query)
    if not cfg:
        return None
    return _query_erd_aggregate(cfg, query, entity)


def _handle_car_recommendation(query: str, entity: dict[str, Any], ctx: ChatContext) -> str | None:
    if not asks_car_recommendation(query):
        return None
    persona = entity.get("persona")
    if not persona:
        return None
    rec = ctx.recommend_fn(persona, ctx.cars_df)
    if rec.empty:
        return f"{persona} 유형 추천 차량이 없습니다."
    lines = []
    for idx, (_, row) in enumerate(rec.head(5).iterrows(), start=1):
        lines.append(
            f"{idx}) {row.get('brand','')} {row.get('car_model','')} - {row.get('reason','')}"
        )
    return f"{persona} 유형 추천 차량입니다.\n" + "\n".join(lines)


def _query_region_persona_from_db(entity: dict[str, Any]) -> str | None:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            params: dict[str, Any] = {"region": entity["region"]}
            if entity.get("year_month"):
                sql = (
                    f"SELECT {_YM}, region, persona_code, eco_ratio, large_ratio, female_ratio, import_ratio "
                    "FROM region_stats WHERE region = :region "
                    f"AND REPLACE(SUBSTRING({_YM}, 1, 7), '-', '') = :ym "
                    f"ORDER BY {_YM} DESC LIMIT 1"
                )
                params["ym"] = _normalize_month(entity["year_month"]).replace("-", "")
            else:
                sql = (
                    f"SELECT {_YM}, region, persona_code, eco_ratio, large_ratio, female_ratio, import_ratio "
                    f"FROM region_stats WHERE region = :region ORDER BY {_YM} DESC LIMIT 1"
                )
            row = conn.execute(text(sql), params).mappings().first()
            if not row:
                return f"{entity['region']} 지역 데이터를 찾을 수 없습니다."
            ym = _normalize_month(str(row["year_month"]))
            return (
                f"{ym} 기준 {row['region']}의 Car-BTI는 {row['persona_code']}입니다. "
                f"(친환경 {float(row['eco_ratio']):.2f}, 대형 {float(row['large_ratio']):.2f}, "
                f"여성 {float(row['female_ratio']):.2f}, 수입 {float(row['import_ratio']):.2f})"
            )
    except Exception as exc:
        logger.warning("지역 페르소나 조회 실패: %s", type(exc).__name__)
        return None


def _query_same_persona_regions_from_db(entity: dict[str, Any]) -> str | None:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            base_params: dict[str, Any] = {"region": entity["region"]}
            if entity.get("year_month"):
                base_sql = (
                    f"SELECT {_YM}, region, persona_code FROM region_stats "
                    f"WHERE region = :region AND REPLACE(SUBSTRING({_YM}, 1, 7), '-', '') = :ym "
                    f"ORDER BY {_YM} DESC LIMIT 1"
                )
                base_params["ym"] = _normalize_month(entity["year_month"]).replace("-", "")
            else:
                base_sql = (
                    f"SELECT {_YM}, region, persona_code FROM region_stats "
                    f"WHERE region = :region ORDER BY {_YM} DESC LIMIT 1"
                )
            base = conn.execute(text(base_sql), base_params).mappings().first()
            if not base:
                return None

            persona = str(base["persona_code"])
            ym_label = _normalize_month(str(base["year_month"]))
            if entity.get("year_month"):
                other_sql = (
                    "SELECT region FROM region_stats "
                    "WHERE persona_code = :persona AND region <> :region "
                    f"AND REPLACE(SUBSTRING({_YM}, 1, 7), '-', '') = :ym ORDER BY region"
                )
                other_params = {"persona": persona, "region": entity["region"], "ym": ym_label.replace("-", "")}
            else:
                other_sql = (
                    "SELECT region FROM region_stats "
                    f"WHERE persona_code = :persona AND region <> :region AND {_YM} = :year_month ORDER BY region"
                )
                other_params = {"persona": persona, "region": entity["region"], "year_month": base["year_month"]}

            others = conn.execute(text(other_sql), other_params).mappings().all()
            if not others:
                return f"{ym_label} 기준 {entity['region']}의 Car-BTI는 {persona}이며, 동일한 다른 지역은 없습니다."
            region_list = ", ".join(str(r["region"]) for r in others)
            return (
                f"{ym_label} 기준 {entity['region']}의 Car-BTI는 {persona}입니다. "
                f"동일한 Car-BTI({persona}) 지역: {region_list}"
            )
    except Exception as exc:
        logger.warning("동일 페르소나 지역 조회 실패: %s", type(exc).__name__)
        return None


def _query_same_persona_regions_from_df(entity: dict[str, Any], df: pd.DataFrame) -> str | None:
    if df.empty or "region" not in df.columns or "persona_code" not in df.columns:
        return None
    work = df.copy()
    if entity.get("year_month") and "year_month" in work.columns:
        target = _normalize_month(entity["year_month"])
        work = work[work["year_month"].astype(str).apply(_normalize_month) == target]
    base = work[work["region"].astype(str) == str(entity["region"])]
    if base.empty:
        return None
    persona = str(base.iloc[0]["persona_code"])
    others = work[(work["persona_code"].astype(str) == persona) & (work["region"].astype(str) != str(entity["region"]))]
    ym = _normalize_month(str(base.iloc[0].get("year_month", "")))
    if others.empty:
        return f"{ym} 기준 {entity['region']}의 Car-BTI는 {persona}이며, 동일한 다른 지역은 없습니다."
    region_list = ", ".join(others["region"].astype(str).tolist())
    return f"{ym} 기준 {entity['region']}의 Car-BTI는 {persona}입니다. 동일한 Car-BTI({persona}) 지역: {region_list}"


def _query_persona_regions_from_db(entity: dict[str, Any], query: str = "") -> str | None:
    persona = str(entity["persona"]).upper()
    try:
        engine = get_engine()
        with engine.connect() as conn:
            persona_meta = conn.execute(
                text(
                    "SELECT persona_name, persona_keyword FROM tbl_persona_detail "
                    "WHERE persona_code = :code LIMIT 1"
                ),
                {"code": persona},
            ).mappings().first()

            if entity.get("year_month"):
                ym = _normalize_month(entity["year_month"]).replace("-", "")
                sql = (
                    f"SELECT {_YM}, region FROM region_stats "
                    f"WHERE persona_code = :persona AND REPLACE(SUBSTRING({_YM}, 1, 7), '-', '') = :ym "
                    "ORDER BY region"
                )
                rows = conn.execute(text(sql), {"persona": persona, "ym": ym}).mappings().all()
                ym_label = _normalize_month(entity["year_month"])
            else:
                latest = conn.execute(text(f"SELECT MAX({_YM}) AS ym FROM region_stats")).mappings().first()
                if not latest or not latest["ym"]:
                    return None
                ym_label = _normalize_month(str(latest["ym"]))
                sql = (
                    f"SELECT {_YM}, region FROM region_stats "
                    f"WHERE persona_code = :persona AND {_YM} = :ym ORDER BY region"
                )
                rows = conn.execute(
                    text(sql),
                    {"persona": persona, "ym": latest["ym"]},
                ).mappings().all()

            if not rows:
                label = persona_meta.get("persona_name", "") if persona_meta else ""
                suffix = f" ({label})" if label else ""
                return f"{ym_label} 기준 {persona}{suffix} 유형에 해당하는 지역은 없습니다."

            regions = ", ".join(str(r["region"]) for r in rows)
            name = (persona_meta or {}).get("persona_name", "")
            keyword = (persona_meta or {}).get("persona_keyword", "")
            header = f"{persona}"
            if name:
                header += f" ({name})"
            if keyword:
                header += f" · {keyword}"

            q = query.lower()
            if any(s in q for s in ["있어", "있나", "있니", "있을까"]):
                return (
                    f"네, {header} 유형에 해당하는 지역이 있습니다.\n"
                    f"{ym_label} 기준: {regions}"
                )
            return f"{ym_label} 기준 {header} 유형 지역: {regions}"
    except Exception as exc:
        logger.warning("페르소나 지역 조회 실패: %s", type(exc).__name__)
        return None


def _extract_region_stats_metric(query: str) -> str | None:
    q = query.lower()
    if any(k in q for k in ["친환경", "전기차", "eco"]):
        return "eco_ratio"
    if any(k in q for k in ["대형", "suv", "large"]):
        return "large_ratio"
    if any(k in q for k in ["여성", "female"]):
        return "female_ratio"
    if any(k in q for k in ["수입", "import"]):
        return "import_ratio"
    return None


def _query_top_regions_from_region_stats(metric_col: str, entity: dict[str, Any]) -> str | None:
    if metric_col not in {"eco_ratio", "large_ratio", "female_ratio", "import_ratio"}:
        return None
    label_map = {
        "eco_ratio": "친환경 비율",
        "large_ratio": "대형 비율",
        "female_ratio": "여성 등록 비율",
        "import_ratio": "수입차 비율",
    }
    try:
        engine = get_engine()
        with engine.connect() as conn:
            top_n = int(entity.get("top_n", 5))
            if entity.get("year_month"):
                ym = _normalize_month(entity["year_month"]).replace("-", "")
                sql = (
                    f"SELECT {_YM}, region, persona_code, {metric_col} AS metric "
                    f"FROM region_stats WHERE REPLACE(SUBSTRING({_YM},1,7),'-','') = :ym "
                    "ORDER BY metric DESC LIMIT :limit_n"
                )
                rows = conn.execute(text(sql), {"ym": ym, "limit_n": top_n}).mappings().all()
                ym_label = _normalize_month(entity["year_month"])
            else:
                latest = conn.execute(text(f"SELECT MAX({_YM}) AS ym FROM region_stats")).mappings().first()
                if not latest or not latest["ym"]:
                    return None
                ym_label = _normalize_month(str(latest["ym"]))
                sql = (
                    f"SELECT {_YM}, region, persona_code, {metric_col} AS metric "
                    f"FROM region_stats WHERE {_YM} = :ym ORDER BY metric DESC LIMIT :limit_n"
                )
                rows = conn.execute(text(sql), {"ym": latest["ym"], "limit_n": top_n}).mappings().all()
            if not rows:
                return None
            parts = [f"{idx+1}) {r['region']} {float(r['metric']):.2f}% ({r['persona_code']})" for idx, r in enumerate(rows)]
            return f"{ym_label} 기준 {label_map[metric_col]} 상위 {len(rows)}개 지역: " + " / ".join(parts)
    except Exception as exc:
        logger.warning("region_stats 상위 조회 실패: %s", type(exc).__name__)
        return None


def _detect_erd_table(query: str) -> dict[str, Any] | None:
    q = query.lower()
    for cfg in ERD_TABLES:
        if any(k in q for k in cfg["keywords"]):
            return cfg
    return None


def _query_erd_aggregate(cfg: dict[str, Any], query: str, entity: dict[str, Any]) -> str | None:
    q = query.lower()
    wants_top = any(k in q for k in ["상위", "top", "가장 많은", "많은 지역", "높은 지역"])
    wants_trend = any(k in q for k in ["추이", "변화", "월별", "최근 6개월", "trend"])
    dim_value = _detect_dim_value(query, cfg)
    try:
        engine = get_engine()
        with engine.connect() as conn:
            if wants_trend and entity.get("region"):
                return _query_erd_trend(conn, cfg, entity, dim_value)
            if wants_top:
                return _query_erd_top(conn, cfg, entity, dim_value)
            return _query_erd_distribution(conn, cfg, entity)
    except Exception as exc:
        logger.warning("ERD 집계 조회 실패: %s", type(exc).__name__)
        return None


def _query_erd_trend(conn: Any, cfg: dict[str, Any], entity: dict[str, Any], dim_value: str | None) -> str | None:
    sql = (
        f"SELECT {_YM}, SUM(reg_count) AS cnt FROM {cfg['table']} "
        "WHERE region = :region "
    )
    params: dict[str, Any] = {"region": entity["region"]}
    if dim_value:
        sql += f"AND {cfg['dim_col']} LIKE :dim_value "
        params["dim_value"] = f"%{dim_value}%"
    sql += f"GROUP BY {_YM} ORDER BY {_YM} DESC LIMIT 6"
    rows = conn.execute(text(sql), params).mappings().all()
    if not rows:
        return None
    parts = [f"{_normalize_month(str(r['year_month']))}: {int(r['cnt']):,}대" for r in rows]
    suffix = f" ({cfg['label']}={dim_value})" if dim_value else ""
    return f"{entity['region']} 월별 등록 추이{suffix}: " + " / ".join(parts)


def _query_erd_top(conn: Any, cfg: dict[str, Any], entity: dict[str, Any], dim_value: str | None) -> str | None:
    top_n = int(entity.get("top_n", 5))
    if entity.get("year_month"):
        ym = _normalize_month(entity["year_month"]).replace("-", "")
        ym_label = _normalize_month(entity["year_month"])
        sql = (
            f"SELECT region, SUM(reg_count) AS cnt FROM {cfg['table']} "
            f"WHERE REPLACE(SUBSTRING({_YM},1,7),'-','') = :ym "
        )
        params: dict[str, Any] = {"ym": ym, "limit_n": top_n}
    else:
        latest = conn.execute(text(f"SELECT MAX({_YM}) AS ym FROM {cfg['table']}")).mappings().first()
        if not latest or not latest["ym"]:
            return None
        ym_label = _normalize_month(str(latest["ym"]))
        sql = (
            f"SELECT region, SUM(reg_count) AS cnt FROM {cfg['table']} "
            f"WHERE {_YM} = :ym "
        )
        params = {"ym": latest["ym"], "limit_n": top_n}

    if dim_value:
        sql += f"AND {cfg['dim_col']} LIKE :dim_value "
        params["dim_value"] = f"%{dim_value}%"
    sql += "GROUP BY region ORDER BY cnt DESC LIMIT :limit_n"
    rows = conn.execute(text(sql), params).mappings().all()
    if not rows:
        return None
    items = [f"{idx+1}) {r['region']} {int(r['cnt']):,}대" for idx, r in enumerate(rows)]
    suffix = f" ({cfg['label']}={dim_value})" if dim_value else ""
    return f"{ym_label} 기준 {cfg['label']} 등록 상위 {len(rows)}개 지역{suffix}: " + " / ".join(items)


def _query_erd_distribution(conn: Any, cfg: dict[str, Any], entity: dict[str, Any]) -> str | None:
    sql = f"SELECT {cfg['dim_col']} AS dim, SUM(reg_count) AS cnt FROM {cfg['table']} WHERE 1=1 "
    params: dict[str, Any] = {"limit_n": int(entity.get("top_n", 5))}
    if entity.get("year_month"):
        sql += f"AND REPLACE(SUBSTRING({_YM},1,7),'-','') = :ym "
        params["ym"] = _normalize_month(entity["year_month"]).replace("-", "")
    if entity.get("region"):
        sql += "AND region = :region "
        params["region"] = entity["region"]
    sql += f"GROUP BY {cfg['dim_col']} ORDER BY cnt DESC LIMIT :limit_n"
    rows = conn.execute(text(sql), params).mappings().all()
    if not rows:
        return None
    scope = []
    if entity.get("year_month"):
        scope.append(f"{_normalize_month(entity['year_month'])} 기준")
    if entity.get("region"):
        scope.append(str(entity["region"]))
    scope_text = " ".join(scope) if scope else "최신 기준"
    items = [f"{r['dim']} {int(r['cnt']):,}대" for r in rows]
    return f"{scope_text} {cfg['label']} 분포: " + " / ".join(items)


def _detect_dim_value(query: str, cfg: dict[str, Any]) -> str | None:
    q = query.lower()
    for key, value in cfg["value_map"].items():
        if key in q:
            return value
    return None


def _build_context(query: str, entity: dict[str, Any], ctx: ChatContext) -> str:
    lines: list[str] = []
    db_rows = _query_generic_region_stats(entity, query)
    if db_rows:
        lines.append("[SQL 조회 결과]")
        lines.extend(f"- {row}" for row in db_rows)
    if not is_stats_query(query):
        faq_rows = search_faq(ctx.faq_df, query, top_k=5, vector_index=ctx.vector_index)
        if faq_rows:
            lines.append("[FAQ 검색 결과]")
            for row in faq_rows:
                lines.append(
                    f"- 회사={row.get('company','')} 질문={row.get('question','')} 답변={row.get('answer','')}"
                )
    return "\n".join(lines)


def _query_generic_region_stats(entity: dict[str, Any], query: str = "") -> list[str]:
    rows: list[str] = []
    metric_col = _extract_region_stats_metric(query)
    if metric_col and any(k in query.lower() for k in ["top", "상위", "가장 높은", "많은 지역", "높은 지역"]):
        direct = _query_top_regions_from_region_stats(metric_col, entity)
        if direct:
            return [direct]

    if entity.get("persona") and asks_persona_region_list(query):
        direct = _query_persona_regions_from_db(entity, query)
        if direct:
            return [direct]

    try:
        engine = get_engine()
        with engine.connect() as conn:
            if entity.get("region"):
                sql = (
                    f"SELECT {_YM}, region, persona_code, eco_ratio, large_ratio, female_ratio, import_ratio "
                    f"FROM region_stats WHERE region = :region ORDER BY {_YM} DESC LIMIT :limit_n"
                )
                result = conn.execute(
                    text(sql),
                    {"region": entity["region"], "limit_n": int(entity.get("top_n", 5))},
                ).mappings().all()
            elif entity.get("persona"):
                sql = (
                    f"SELECT {_YM}, region, persona_code, eco_ratio, large_ratio, female_ratio, import_ratio "
                    f"FROM region_stats WHERE persona_code = :persona ORDER BY {_YM} DESC, region LIMIT :limit_n"
                )
                result = conn.execute(
                    text(sql),
                    {"persona": entity["persona"], "limit_n": int(entity.get("top_n", 5))},
                ).mappings().all()
            else:
                sql = (
                    f"SELECT {_YM}, region, persona_code, eco_ratio, large_ratio, female_ratio, import_ratio "
                    f"FROM region_stats ORDER BY {_YM} DESC, region LIMIT :limit_n"
                )
                result = conn.execute(text(sql), {"limit_n": int(entity.get("top_n", 5))}).mappings().all()

            for r in result:
                rows.append(
                    f"{_normalize_month(str(r['year_month']))} {r['region']} persona={r['persona_code']} "
                    f"(친환경 {float(r['eco_ratio']):.2f}, 대형 {float(r['large_ratio']):.2f}, "
                    f"여성 {float(r['female_ratio']):.2f}, 수입 {float(r['import_ratio']):.2f})"
                )
    except Exception as exc:
        logger.warning("기본 region_stats 조회 실패: %s", type(exc).__name__)
    return rows


def _fallback_answer(query: str, context_text: str) -> str:
    sql_lines: list[str] = []
    faq_lines: list[str] = []
    section = ""
    for raw in context_text.splitlines():
        line = raw.strip()
        if line == "[SQL 조회 결과]":
            section = "sql"
            continue
        if line == "[FAQ 검색 결과]":
            section = "faq"
            continue
        if not line.startswith("- "):
            continue
        item = line[2:]
        if section == "sql":
            sql_lines.append(item)
        elif section == "faq":
            faq_lines.append(item)
    if sql_lines:
        if ("car-bti" in query.lower()) or ("페르소나" in query):
            return f"최근 Car-BTI 조회 결과: {sql_lines[0]}"
        if is_stats_query(query) and any(k in query.lower() for k in ["상위", "top"]):
            return sql_lines[0]
        return f"DB 조회 결과: {sql_lines[0]}"
    if is_stats_query(query):
        return "지역 통계 조회에 실패했습니다. DB 연결과 region_stats 데이터를 확인해 주세요."
    if faq_lines:
        return f"FAQ 조회 결과: {faq_lines[0]}"
    return "조회된 데이터가 없습니다."


def _normalize_month(value: str) -> str:
    s = str(value).strip()
    if re.fullmatch(r"20\d{2}-[01]\d", s):
        return s
    if re.fullmatch(r"20\d{2}[01]\d", s):
        return f"{s[:4]}-{s[4:6]}"
    if re.fullmatch(r"20\d{2}-[01]\d-\d{2}", s):
        return s[:7]
    return s
