"""
chatbot/llm_client.py
=====================
LLM(대화) + 임베딩(검색) 호출을 한 곳으로 추상화한다.

- 벤더: Google Gemini (google-genai SDK)
    · 대화  : gemini-2.5-flash (무료 티어)
    · 임베딩 : gemini-embedding-001 (무료 티어, FAQ 임베딩은 기본 OFF)
- 환경변수
    GEMINI_API_KEY             : (필수) Google AI Studio에서 발급한 키
    GEMINI_CHAT_MODEL          : (선택) 대화 모델, 기본 gemini-2.5-flash
    GEMINI_EMBED_MODEL         : (선택) 임베딩 모델, 기본 gemini-embedding-001
    GEMINI_MAX_OUTPUT_TOKENS   : (선택) 답변 최대 토큰, 기본 1024
    GEMINI_MIN_REQUEST_INTERVAL: (선택) API 호출 최소 간격(초), 기본 2.0
    GEMINI_MAX_RETRIES         : (선택) 429 시 재시도 횟수, 기본 3
    GEMINI_FAQ_EMBEDDING       : (선택) FAQ 임베딩 검색 사용(1=켜기), 기본 0

키/패키지가 없으면 is_available()가 False를 돌려주고,
챗봇은 자동으로 "규칙 기반 폴백 모드"로 동작한다. (앱이 죽지 않음)
"""

from __future__ import annotations

import os
import threading
import time
from functools import lru_cache

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

DEFAULT_CHAT_MODEL = os.getenv("GEMINI_CHAT_MODEL", "gemini-2.5-flash")
DEFAULT_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")
DEFAULT_MAX_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "1024"))
DEFAULT_MIN_INTERVAL = float(os.getenv("GEMINI_MIN_REQUEST_INTERVAL", "2.0"))
DEFAULT_MAX_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "3"))

_throttle_lock = threading.Lock()
_last_request_at = 0.0


class RateLimitError(Exception):
    """Gemini 429 / RESOURCE_EXHAUSTED."""


def _api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def has_api_key() -> bool:
    """GEMINI_API_KEY(또는 GOOGLE_API_KEY)가 설정되어 있는지."""
    return bool(_api_key())


def faq_embedding_enabled() -> bool:
    """FAQ 의미 검색(임베딩 API) 사용 여부. 무료 티어에서는 기본 OFF."""
    return os.getenv("GEMINI_FAQ_EMBEDDING", "0").strip().lower() in ("1", "true", "yes", "on")


def _is_rate_limit_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "resource_exhausted" in msg or "too many requests" in msg


def _throttle() -> None:
    """연속 API 호출 간 최소 간격을 둔다 (무료 티어 RPM 완화)."""
    global _last_request_at
    with _throttle_lock:
        now = time.monotonic()
        wait = DEFAULT_MIN_INTERVAL - (now - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()


def _call_with_retry(fn):
    """429 발생 시 지수 백오프로 재시도."""
    last_exc: Exception | None = None
    for attempt in range(DEFAULT_MAX_RETRIES):
        try:
            _throttle()
            return fn()
        except Exception as exc:
            last_exc = exc
            if _is_rate_limit_error(exc) and attempt < DEFAULT_MAX_RETRIES - 1:
                time.sleep(2 ** attempt * 2)  # 2s, 4s, 8s …
                continue
            if _is_rate_limit_error(exc):
                raise RateLimitError(str(exc)) from exc
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("API 호출 실패")


@lru_cache(maxsize=1)
def is_available() -> bool:
    """LLM 호출이 가능한 환경인지 (키 + google-genai 패키지)."""
    if not _api_key():
        return False
    try:
        from google import genai  # noqa: F401

        return True
    except Exception:
        return False


@lru_cache(maxsize=1)
def _client():
    from google import genai

    return genai.Client(api_key=_api_key())


def _to_gemini(messages: list[dict]) -> tuple[str, list[dict]]:
    """OpenAI 스타일 messages → (system_instruction, Gemini contents)."""
    system_parts: list[str] = []
    contents: list[dict] = []
    for m in messages:
        role = m.get("role")
        text = m.get("content", "") or ""
        if role == "system":
            if text:
                system_parts.append(text)
        elif role in ("user", "assistant"):
            g_role = "model" if role == "assistant" else "user"
            contents.append({"role": g_role, "parts": [{"text": text}]})

    while contents and contents[0]["role"] == "model":
        contents.pop(0)

    return "\n\n".join(system_parts), contents


def chat(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int | None = None,
) -> str:
    """대화 메시지 리스트 → 어시스턴트 답변 텍스트."""
    from google.genai import types

    system_instruction, contents = _to_gemini(messages)
    config = types.GenerateContentConfig(
        system_instruction=system_instruction or None,
        temperature=temperature,
        max_output_tokens=max_tokens or DEFAULT_MAX_OUTPUT_TOKENS,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    def _do_call():
        return _client().models.generate_content(
            model=model or DEFAULT_CHAT_MODEL,
            contents=contents,
            config=config,
        )

    resp = _call_with_retry(_do_call)
    text = (resp.text or "").strip()

    try:
        candidate = (resp.candidates or [None])[0]
        finish = getattr(candidate, "finish_reason", None)
        finish_str = str(finish).upper() if finish is not None else ""
        if "MAX_TOKENS" in finish_str and text:
            text += "\n\n_(답변이 길어 일부 생략되었을 수 있어요. 더 짧게 다시 물어보시면 도와드릴게요.)_"
    except Exception:
        pass

    return text


def embed(texts: list[str], model: str | None = None) -> list[list[float]]:
    """텍스트 리스트 → 임베딩 벡터 리스트. (대량은 배치로 나눠 호출)"""
    model = model or DEFAULT_EMBED_MODEL
    vectors: list[list[float]] = []
    batch_size = 100

    for start in range(0, len(texts), batch_size):
        chunk = texts[start : start + batch_size]

        def _do_embed(batch=chunk):
            return _client().models.embed_content(model=model, contents=batch)

        resp = _call_with_retry(_do_embed)
        vectors.extend(list(e.values) for e in resp.embeddings)
    return vectors
