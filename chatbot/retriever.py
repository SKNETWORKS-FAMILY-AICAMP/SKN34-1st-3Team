from __future__ import annotations

import os
import re
from typing import Any

import pandas as pd

from chatbot.embeddings import is_embedding_enabled
from chatbot.vector_store import VectorIndex

SEMANTIC_WEIGHT = float(os.getenv("FAQ_SEMANTIC_WEIGHT", "0.55"))
KEYWORD_WEIGHT = float(os.getenv("FAQ_KEYWORD_WEIGHT", "0.30"))
COMPANY_WEIGHT = float(os.getenv("FAQ_COMPANY_WEIGHT", "0.15"))
MIN_HYBRID_SCORE = float(os.getenv("FAQ_MIN_HYBRID_SCORE", "0.12"))

STATS_QUERY_KEYWORDS = [
    "상위", "top", "car-bti", "페르소나", "비율", "통계", "등록", "지역", "시도",
    "추이", "분포", "몇", "얼마", "같은", "동일", "똑같", "친환경", "대형", "여성", "수입",
]


def is_stats_query(query: str) -> bool:
    q = query.lower()
    return any(k in q for k in STATS_QUERY_KEYWORDS)


def should_try_faq(query: str) -> bool:
    q = query.lower()
    if any(k in q for k in ["faq", "자주 묻는"]):
        return True

    stats_keywords = [
        "상위", "top", "car-bti", "페르소나", "비율", "통계", "등록", "지역", "시도",
        "추이", "분포", "몇", "얼마", "같은", "동일", "똑같",
    ]
    if any(k in q for k in stats_keywords):
        return False

    faq_topics = [
        "충전", "보조금", "보험", "정비", "유지비", "서비스", "배터리", "보증",
        "as", "수리", "리콜", "내비", "블루링크", "카페이", "계정", "앱",
    ]
    company_terms, topic_terms = _split_query_terms(q)
    if company_terms and topic_terms:
        return True
    if company_terms and any(t in q for t in faq_topics):
        return True
    if any(k in q for k in ["질문", "답변"]) and (company_terms or topic_terms):
        return True
    return False


def search_faq(
    faq_df: pd.DataFrame,
    query: str,
    top_k: int = 5,
    vector_index: VectorIndex | None = None,
) -> list[dict[str, Any]]:
    keyword_rows = _keyword_search(faq_df, query, top_k=top_k * 2)
    if not vector_index or not vector_index.is_ready() or not is_embedding_enabled():
        return keyword_rows[:top_k]

    company_terms, _ = _split_query_terms(query.lower())
    company_filter = company_terms[0] if len(company_terms) == 1 else None
    semantic_rows = vector_index.search_faq(query, top_k=top_k * 2, company=company_filter)
    if not semantic_rows and company_terms:
        semantic_rows = vector_index.search_faq(query, top_k=top_k * 2)

    merged = _merge_hybrid_results(keyword_rows, semantic_rows, query, top_k)
    return merged or keyword_rows[:top_k]


def _keyword_search(faq_df: pd.DataFrame, query: str, top_k: int = 5) -> list[dict[str, Any]]:
    if faq_df.empty:
        return []

    q = query.lower()
    scored = faq_df.copy()
    question = scored.get("question", pd.Series(dtype=str)).fillna("").astype(str)
    answer = scored.get("answer", pd.Series(dtype=str)).fillna("").astype(str)
    company = scored.get("company", pd.Series(dtype=str)).fillna("").astype(str)
    tags = scored.get("persona_tags", pd.Series(dtype=str)).fillna("").astype(str)

    company_terms, topic_terms = _split_query_terms(q)
    all_terms = company_terms + topic_terms
    pattern = "|".join(_tokenize_for_regex(" ".join(all_terms)))
    topic_pattern = "|".join(_tokenize_for_regex(" ".join(topic_terms))) if topic_terms else ""
    company_pattern = "|".join(_tokenize_for_regex(" ".join(company_terms))) if company_terms else ""

    scored["_topic_score"] = (
        question.str.lower().str.count(topic_pattern) * 4
        + answer.str.lower().str.count(topic_pattern) * 2
        + tags.str.lower().str.count(topic_pattern) * 3
    ) if topic_pattern else 0
    scored["_company_score"] = (
        company.str.lower().str.count(company_pattern) * 4
        + question.str.lower().str.count(company_pattern) * 1
    ) if company_pattern else 0
    scored["_base_score"] = (
        question.str.lower().str.count(pattern) * 2
        + answer.str.lower().str.count(pattern) * 1
        + company.str.lower().str.count(pattern) * 1
        + tags.str.lower().str.count(pattern) * 1
    ) if pattern else 0
    scored["_score"] = scored["_base_score"] + scored["_topic_score"] + scored["_company_score"]

    if topic_terms:
        topic_matched = scored[scored["_topic_score"] > 0]
        if not topic_matched.empty:
            scored = topic_matched

    if company_terms:
        company_matched = scored[scored["_company_score"] > 0]
        if not company_matched.empty:
            scored = company_matched

    scored = scored.sort_values("_score", ascending=False).head(top_k)
    scored = scored[scored["_score"] > 0]
    if scored.empty:
        return []

    raw_max = float(scored["_score"].max())
    rows = scored.to_dict(orient="records")
    enriched: list[dict[str, Any]] = []
    for row in rows:
        raw = float(row.pop("_score", 0.0))
        row.pop("_base_score", None)
        row.pop("_topic_score", None)
        row.pop("_company_score", None)
        row["_keyword_score"] = _normalize_keyword_score(raw, raw_max)
        enriched.append(row)
    return enriched


def _merge_hybrid_results(
    keyword_rows: list[dict[str, Any]],
    semantic_rows: list[dict[str, Any]],
    query: str,
    top_k: int,
) -> list[dict[str, Any]]:
    company_terms, _ = _split_query_terms(query.lower())
    merged: dict[str, dict[str, Any]] = {}

    for row in keyword_rows:
        key = _row_key(row)
        merged[key] = {
            **row,
            "_keyword_score": float(row.get("_keyword_score", 0.0)),
            "_semantic_score": float(row.get("_semantic_score", 0.0)),
        }

    for row in semantic_rows:
        key = _row_key(row)
        semantic_score = float(row.get("_semantic_score", 0.0))
        if key in merged:
            merged[key]["_semantic_score"] = max(merged[key].get("_semantic_score", 0.0), semantic_score)
        else:
            merged[key] = {**row, "_keyword_score": 0.0, "_semantic_score": semantic_score}

    results: list[dict[str, Any]] = []
    for row in merged.values():
        company_match = 1.0 if company_terms and any(c in str(row.get("company", "")).lower() for c in company_terms) else 0.0
        hybrid = (
            SEMANTIC_WEIGHT * float(row.get("_semantic_score", 0.0))
            + KEYWORD_WEIGHT * float(row.get("_keyword_score", 0.0))
            + COMPANY_WEIGHT * company_match
        )
        if hybrid < MIN_HYBRID_SCORE and float(row.get("_keyword_score", 0.0)) <= 0:
            continue
        cleaned = {k: v for k, v in row.items() if not str(k).startswith("_")}
        cleaned["_hybrid_score"] = hybrid
        results.append(cleaned)

    results.sort(key=lambda r: float(r.get("_hybrid_score", 0.0)), reverse=True)
    for row in results:
        row.pop("_hybrid_score", None)
    return results[:top_k]


def _row_key(row: dict[str, Any]) -> str:
    if row.get("faq_id") is not None:
        return f"faq:{row['faq_id']}"
    return f"q:{row.get('company','')}|{row.get('question','')}"


def _normalize_keyword_score(score: float, max_score: float) -> float:
    if max_score <= 0:
        return 0.0
    return max(0.0, min(1.0, score / max_score))


def _tokenize_for_regex(query: str) -> list[str]:
    tokens = [t.strip() for t in query.split() if t.strip()]
    safe = []
    for t in tokens[:8]:
        if len(t) >= 2:
            safe.append(re.escape(t))
    return safe or [re.escape(query)]


def _split_query_terms(query: str) -> tuple[list[str], list[str]]:
    companies = ["현대", "기아", "제네시스", "bmw", "벤츠", "테슬라", "볼보", "아우디", "쉐보레", "르노", "k car", "kcar"]
    stopwords = {
        "알려줘", "알려", "뭐야", "무엇", "어떤", "관련", "faq", "질문", "답변", "좀", "해줘",
        "대한", "에서", "그리고", "기준", "최근", "지역", "차량", "요약", "설명", "알고", "싶어",
    }
    raw_tokens = [t.strip() for t in re.split(r"\s+", query) if t.strip()]
    company_terms = [t for t in raw_tokens if any(c in t for c in companies)]
    topic_terms = [t for t in raw_tokens if t not in company_terms and t not in stopwords and len(t) >= 2]
    return company_terms, topic_terms
