"""
chatbot/retriever.py
====================
company_faq 데이터에서 사용자 질문과 관련 있는 FAQ Top-K를 찾아 반환한다. (RAG의 검색 단계)

검색 모드
---------
1. 키워드 모드 (기본) : API 호출 없음 — 무료 티어 429 방지
2. 임베딩 모드        : GEMINI_FAQ_EMBEDDING=1 일 때만 (의미 기반, 코퍼스 디스크 캐시)
"""

from __future__ import annotations

import hashlib
import os
import pickle
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from . import llm_client

_EMB_CACHE: dict[str, np.ndarray] = {}
_CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
_CACHE_FILE = _CACHE_DIR / "faq_embeddings.pkl"

# FAQ 검색 최소 점수 (이하이면 '관련 없음' 처리)
DEFAULT_MIN_KEYWORD_SCORE = float(os.getenv("FAQ_MIN_KEYWORD_SCORE", "0.9"))
DEFAULT_MIN_EMBED_SCORE = float(os.getenv("FAQ_MIN_EMBED_SCORE", "0.55"))


def _doc_text(row: pd.Series) -> str:
    q = str(row.get("question", "") or "")
    a = str(row.get("answer", "") or "")
    return f"{q}\n{a}".strip()


def _stable_fingerprint(docs: list[str]) -> str:
    """프로세스 간 동일한 코퍼스 지문 (디스크 캐시용)."""
    h = hashlib.sha256()
    h.update(str(len(docs)).encode())
    for d in docs:
        h.update(d.encode("utf-8", errors="ignore"))
        h.update(b"\0")
    return h.hexdigest()


# ────────────────────────────────────────
# 키워드(기본) 검색
# ────────────────────────────────────────
def _tokenize(text: str) -> set[str]:
    text = (text or "").lower()
    words = re.findall(r"[0-9a-z]+|[가-힣]+", text)
    tokens: set[str] = set()
    for w in words:
        tokens.add(w)
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
# 임베딩 검색 (선택)
# ────────────────────────────────────────
def _load_disk_cache(key: str) -> np.ndarray | None:
    if not _CACHE_FILE.exists():
        return None
    try:
        with _CACHE_FILE.open("rb") as f:
            data = pickle.load(f)
        if data.get("key") == key:
            return np.asarray(data["vecs"], dtype=float)
    except Exception:
        return None
    return None


def _save_disk_cache(key: str, vecs: np.ndarray) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with _CACHE_FILE.open("wb") as f:
            pickle.dump({"key": key, "vecs": vecs}, f)
    except Exception:
        pass


def _corpus_embeddings(docs: list[str]) -> np.ndarray | None:
    key = _stable_fingerprint(docs)
    if key in _EMB_CACHE:
        return _EMB_CACHE[key]

    disk = _load_disk_cache(key)
    if disk is not None:
        _EMB_CACHE[key] = disk
        return disk

    try:
        vecs = np.asarray(llm_client.embed(docs), dtype=float)
    except Exception:
        return None

    _EMB_CACHE[key] = vecs
    _save_disk_cache(key, vecs)
    return vecs


@lru_cache(maxsize=128)
def _query_embedding(query: str) -> tuple[float, ...] | None:
    """질문 임베딩 캐시 (동일 질문 재호출 방지)."""
    try:
        vec = llm_client.embed([query])[0]
        return tuple(vec)
    except Exception:
        return None


def _cosine_scores(query: str, corpus_vecs: np.ndarray) -> np.ndarray | None:
    q_tuple = _query_embedding(query)
    if q_tuple is None:
        return None
    q_vec = np.asarray(q_tuple, dtype=float)
    corpus_norm = np.linalg.norm(corpus_vecs, axis=1)
    q_norm = np.linalg.norm(q_vec)
    denom = corpus_norm * q_norm
    denom[denom == 0] = 1e-9
    return (corpus_vecs @ q_vec) / denom


# ────────────────────────────────────────
# 공개 API
# ────────────────────────────────────────
def search_faq(query: str, faq_df: pd.DataFrame, top_k: int = 3) -> list[dict]:
    """질문과 관련 있는 FAQ Top-K를 [{company, question, answer, score}] 로 반환."""
    if faq_df is None or faq_df.empty or not query.strip():
        return []

    docs = [_doc_text(row) for _, row in faq_df.iterrows()]

    scores = None
    used_embedding = False
    if llm_client.is_available() and llm_client.faq_embedding_enabled():
        corpus_vecs = _corpus_embeddings(docs)
        if corpus_vecs is not None:
            scores = _cosine_scores(query, corpus_vecs)
            used_embedding = scores is not None

    if scores is None:
        scores = _keyword_scores(query, docs)

    if scores is None or len(scores) == 0 or float(np.max(scores)) <= 0:
        return []

    min_score = DEFAULT_MIN_EMBED_SCORE if used_embedding else DEFAULT_MIN_KEYWORD_SCORE

    top_idx = np.argsort(scores)[::-1][:top_k]
    results: list[dict] = []
    for i in top_idx:
        if scores[i] < min_score:
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
