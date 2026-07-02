"""FAQ 검색 (기본: 키워드, 선택: OpenAI 임베딩)."""

from __future__ import annotations

import os
import re
from typing import Any

import pandas as pd

_EMBED_CACHE: dict[str, list[float]] = {}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _tokenize(text: str) -> set[str]:
    text = re.sub(r"[^\w가-힣]+", " ", str(text).lower())
    tokens = {t for t in text.split() if len(t) >= 2}
    chars = re.findall(r"[가-힣]{2,}", str(text))
    tokens.update(chars)
    return tokens


def _keyword_score(query: str, question: str, answer: str, company: str = "") -> float:
    q_tokens = _tokenize(query)
    if not q_tokens:
        return 0.0
    field_tokens = _tokenize(f"{question} {answer} {company}")
    overlap = len(q_tokens & field_tokens)
    if overlap == 0:
        return 0.0
    base = overlap / max(len(q_tokens), 1)
    if any(t in question.lower() for t in q_tokens if len(t) >= 3):
        base += 0.15
    return min(base, 1.0)


def search_faq_keyword(
    query: str,
    faq_df: pd.DataFrame,
    *,
    top_k: int = 3,
    min_score: float | None = None,
) -> list[dict[str, Any]]:
    if faq_df.empty or not query.strip():
        return []

    threshold = min_score if min_score is not None else _env_float("FAQ_MIN_KEYWORD_SCORE", 0.15)
    rows: list[dict[str, Any]] = []

    for _, row in faq_df.iterrows():
        q = str(row.get("question", ""))
        a = str(row.get("answer", ""))
        company = str(row.get("company", ""))
        score = _keyword_score(query, q, a, company)
        if score >= threshold:
            rows.append({
                "faq_id": row.get("faq_id"),
                "company": company,
                "question": q,
                "answer": a,
                "score": score,
            })

    rows.sort(key=lambda x: x["score"], reverse=True)
    return rows[:top_k]


def _use_embedding() -> bool:
    return os.getenv("OPENAI_FAQ_EMBEDDING", "0").strip() in ("1", "true", "True")


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _embed_texts(texts: list[str]) -> list[list[float]]:
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
    to_fetch = [t for t in texts if t not in _EMBED_CACHE]
    if to_fetch:
        resp = client.embeddings.create(model=model, input=to_fetch)
        for item, text in zip(resp.data, to_fetch):
            _EMBED_CACHE[text] = item.embedding
    return [_EMBED_CACHE[t] for t in texts]


def search_faq(
    query: str,
    faq_df: pd.DataFrame,
    *,
    top_k: int = 3,
    min_score: float | None = None,
) -> list[dict[str, Any]]:
    """FAQ 검색 진입점. 임베딩 OFF면 키워드 검색."""
    if _use_embedding() and os.getenv("OPENAI_API_KEY"):
        try:
            return _search_faq_embedding(query, faq_df, top_k=top_k, min_score=min_score)
        except Exception:
            pass
    return search_faq_keyword(query, faq_df, top_k=top_k, min_score=min_score)


def _search_faq_embedding(
    query: str,
    faq_df: pd.DataFrame,
    *,
    top_k: int = 3,
    min_score: float | None = None,
) -> list[dict[str, Any]]:
    if faq_df.empty:
        return []
    threshold = min_score if min_score is not None else 0.35
    texts = [
        f"{row.get('question', '')} {row.get('answer', '')}"
        for _, row in faq_df.iterrows()
    ]
    all_texts = [query] + texts
    vectors = _embed_texts(all_texts)
    q_vec = vectors[0]
    rows: list[dict[str, Any]] = []
    for (_, row), vec in zip(faq_df.iterrows(), vectors[1:]):
        score = _cosine(q_vec, vec)
        if score >= threshold:
            rows.append({
                "faq_id": row.get("faq_id"),
                "company": str(row.get("company", "")),
                "question": str(row.get("question", "")),
                "answer": str(row.get("answer", "")),
                "score": score,
            })
    rows.sort(key=lambda x: x["score"], reverse=True)
    return rows[:top_k]
