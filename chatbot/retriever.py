"""
chatbot/retriever.py
====================
company_faq 데이터에서 사용자 질문과 관련 있는 FAQ Top-K를 찾아 반환한다. (RAG의 검색 단계)

두 가지 모드
------------
1. 임베딩 모드 : Gemini 키가 있으면 FAQ 전체를 임베딩해 코사인 유사도로 검색 (의미 기반)
2. 키워드 모드 : 키가 없으면 토큰/문자 n-gram 겹침 점수로 검색 (폴백)

FAQ 규모(수백~수천 건)에서는 별도 벡터DB 없이 numpy 배열만으로 충분하다.
임베딩 결과는 모듈 전역에 캐싱해 앱 실행 중 1회만 계산한다.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from . import llm_client

# 임베딩 캐시: {corpus_fingerprint: np.ndarray}
_EMB_CACHE: dict[int, np.ndarray] = {}


def _doc_text(row: pd.Series) -> str:
    q = str(row.get("question", "") or "")
    a = str(row.get("answer", "") or "")
    return f"{q}\n{a}".strip()


def _fingerprint(docs: list[str]) -> int:
    """코퍼스가 바뀌면 캐시를 새로 만들기 위한 지문."""
    return hash((len(docs), tuple(docs)))


# ────────────────────────────────────────
# 키워드(폴백) 검색
# ────────────────────────────────────────
def _tokenize(text: str) -> set[str]:
    text = (text or "").lower()
    words = re.findall(r"[0-9a-z]+|[가-힣]+", text)
    tokens: set[str] = set()
    for w in words:
        tokens.add(w)
        # 한글은 2글자 단위 부분매칭까지 추가 (조사/어미 변형 대응)
        if len(w) >= 2 and re.match(r"[가-힣]+", w):
            tokens.update(w[i : i + 2] for i in range(len(w) - 1))
    return tokens


def _keyword_scores(query: str, docs: list[str]) -> np.ndarray:
    q_tokens = _tokenize(query)
    if not q_tokens:
        return np.zeros(len(docs))
    scores = []
    for d in docs:
        d_tokens = _tokenize(d)
        inter = len(q_tokens & d_tokens)
        scores.append(inter / (len(q_tokens) ** 0.5 + 1e-9))
    return np.array(scores, dtype=float)


# ────────────────────────────────────────
# 임베딩 검색
# ────────────────────────────────────────
def _corpus_embeddings(docs: list[str]) -> np.ndarray | None:
    key = _fingerprint(docs)
    if key in _EMB_CACHE:
        return _EMB_CACHE[key]
    try:
        vecs = np.asarray(llm_client.embed(docs), dtype=float)
    except Exception:
        return None
    _EMB_CACHE[key] = vecs
    return vecs


def _cosine_scores(query: str, corpus_vecs: np.ndarray) -> np.ndarray | None:
    try:
        q_vec = np.asarray(llm_client.embed([query])[0], dtype=float)
    except Exception:
        return None
    corpus_norm = np.linalg.norm(corpus_vecs, axis=1)
    q_norm = np.linalg.norm(q_vec)
    denom = corpus_norm * q_norm
    denom[denom == 0] = 1e-9
    return (corpus_vecs @ q_vec) / denom


# ────────────────────────────────────────
# 공개 API
# ────────────────────────────────────────
def search_faq(query: str, faq_df: pd.DataFrame, top_k: int = 4) -> list[dict]:
    """질문과 관련 있는 FAQ Top-K를 [{company, question, answer, score}] 로 반환."""
    if faq_df is None or faq_df.empty or not query.strip():
        return []

    docs = [_doc_text(row) for _, row in faq_df.iterrows()]

    scores = None
    if llm_client.is_available():
        corpus_vecs = _corpus_embeddings(docs)
        if corpus_vecs is not None:
            scores = _cosine_scores(query, corpus_vecs)

    if scores is None:  # 임베딩 불가 → 키워드 폴백
        scores = _keyword_scores(query, docs)

    if scores is None or len(scores) == 0 or float(np.max(scores)) <= 0:
        return []

    top_idx = np.argsort(scores)[::-1][:top_k]
    results: list[dict] = []
    for i in top_idx:
        if scores[i] <= 0:
            continue
        row = faq_df.iloc[int(i)]
        results.append(
            {
                "company": str(row.get("company", "") or ""),
                "question": str(row.get("question", "") or ""),
                "answer": str(row.get("answer", "") or ""),
                "score": float(scores[i]),
            }
        )
    return results
