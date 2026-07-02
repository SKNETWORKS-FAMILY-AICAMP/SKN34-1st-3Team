from __future__ import annotations

import logging
import os
import time
from typing import Sequence

logger = logging.getLogger(__name__)

_client = None
_last_request_at = 0.0
_local_model = None


def embedding_provider() -> str:
    """openai | local | auto"""
    return os.getenv("EMBEDDING_PROVIDER", "auto").strip().lower()


def local_embedding_model_name() -> str:
    return os.getenv(
        "LOCAL_EMBEDDING_MODEL",
        "paraphrase-multilingual-MiniLM-L12-v2",
    )


def resolve_provider() -> str:
    provider = embedding_provider()
    if provider in {"openai", "local"}:
        return provider
    # auto: OpenAI 키가 없거나 로컬 강제 시 local, 아니면 openai
    if os.getenv("EMBEDDING_FORCE_LOCAL", "0").strip().lower() in {"1", "true", "yes", "on"}:
        return "local"
    if not os.getenv("OPENAI_API_KEY"):
        return "local"
    return "openai"


def is_embedding_enabled() -> bool:
    if os.getenv("OPENAI_FAQ_EMBEDDING", "1").strip().lower() not in {"1", "true", "yes", "on"}:
        return False
    provider = resolve_provider()
    if provider == "local":
        return True
    return bool(os.getenv("OPENAI_API_KEY"))


def get_embedding_info() -> dict[str, str]:
    provider = resolve_provider()
    if provider == "local":
        return {"provider": "local", "model": local_embedding_model_name()}
    return {"provider": "openai", "model": os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")}


def openai_embedding_model() -> str:
    return os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


def _get_openai_client():
    global _client
    if _client is None:
        from openai import OpenAI

        _client = OpenAI(timeout=60.0)
    return _client


def _get_local_model():
    global _local_model
    if _local_model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "로컬 임베딩을 사용하려면 sentence-transformers가 필요합니다. "
                "pip install sentence-transformers"
            ) from exc
        logger.info("로컬 임베딩 모델 로드 중: %s", local_embedding_model_name())
        _local_model = SentenceTransformer(local_embedding_model_name())
    return _local_model


def _throttle() -> None:
    global _last_request_at
    interval = float(os.getenv("OPENAI_MIN_REQUEST_INTERVAL", "1.0"))
    if interval <= 0:
        return
    elapsed = time.monotonic() - _last_request_at
    if elapsed < interval:
        time.sleep(interval - elapsed)
    _last_request_at = time.monotonic()


def _is_quota_error(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    return (
        "insufficient_quota" in text
        or "quota" in text
        or "billing" in text
        or "ratelimit" in name and "quota" in text
    )


def _is_rate_limit_error(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    return "rate_limit" in name or "rate limit" in text or "429" in text


def embed_texts(texts: Sequence[str], batch_size: int | None = None) -> list[list[float]]:
    if not texts:
        return []
    if not is_embedding_enabled():
        raise RuntimeError("임베딩이 비활성화되어 있습니다. OPENAI_FAQ_EMBEDDING=1 로 설정하세요.")

    provider = resolve_provider()
    if provider == "local":
        return _embed_texts_local(texts, batch_size or int(os.getenv("LOCAL_EMBEDDING_BATCH_SIZE", "32")))

    try:
        return _embed_texts_openai(texts, batch_size or int(os.getenv("OPENAI_EMBEDDING_BATCH_SIZE", "16")))
    except RuntimeError as exc:
        if _is_quota_error(exc) or "insufficient_quota" in str(exc).lower():
            logger.warning("OpenAI 할당량 부족 → 로컬 임베딩으로 자동 전환합니다.")
            return _embed_texts_local(texts, batch_size or 32)
        raise


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]


def _embed_texts_local(texts: Sequence[str], batch_size: int) -> list[list[float]]:
    model = _get_local_model()
    vectors: list[list[float]] = []
    trimmed = [t[:4000] for t in texts]
    for start in range(0, len(trimmed), batch_size):
        chunk = trimmed[start : start + batch_size]
        encoded = model.encode(chunk, normalize_embeddings=True, show_progress_bar=False)
        vectors.extend(encoded.tolist())
    return vectors


def _embed_texts_openai(texts: Sequence[str], batch_size: int) -> list[list[float]]:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY가 없습니다.")

    client = _get_openai_client()
    model = openai_embedding_model()
    vectors: list[list[float]] = []
    retries = int(os.getenv("OPENAI_MAX_RETRIES", "5"))

    for start in range(0, len(texts), batch_size):
        chunk = [t[:8000] for t in texts[start : start + batch_size]]
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                _throttle()
                resp = client.embeddings.create(model=model, input=chunk)
                vectors.extend([item.embedding for item in resp.data])
                break
            except Exception as exc:
                last_exc = exc
                if _is_quota_error(exc):
                    raise RuntimeError(f"OpenAI 할당량 부족(insufficient_quota): {exc}") from exc
                wait = min(2 ** attempt * 2, 30)
                logger.warning(
                    "OpenAI 임베딩 배치 실패(%s/%s): %s → %ss 후 재시도",
                    attempt + 1,
                    retries,
                    type(exc).__name__,
                    wait,
                )
                time.sleep(wait)
        else:
            raise RuntimeError(f"OpenAI 임베딩 생성 실패: {last_exc}")
    return vectors
