"""
chatbot/llm_client.py
=====================
LLM(대화) + 임베딩(검색) 호출을 한 곳으로 추상화한다.

- 벤더: Google Gemini (google-genai SDK)
    · 대화  : gemini-2.5-flash (무료 티어)
    · 임베딩 : gemini-embedding-001 (무료 티어)
- 환경변수
    GEMINI_API_KEY        : (필수) Google AI Studio에서 발급한 키
                            (GOOGLE_API_KEY 로 설정해도 인식)
    GEMINI_CHAT_MODEL     : (선택) 대화 모델, 기본 gemini-2.5-flash
    GEMINI_EMBED_MODEL    : (선택) 임베딩 모델, 기본 text-embedding-004

키/패키지가 없으면 is_available()가 False를 돌려주고,
챗봇은 자동으로 "규칙 기반 폴백 모드"로 동작한다. (앱이 죽지 않음)
"""

from __future__ import annotations

import os
from functools import lru_cache

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

DEFAULT_CHAT_MODEL = os.getenv("GEMINI_CHAT_MODEL", "gemini-2.5-flash")
DEFAULT_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")


def _api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def has_api_key() -> bool:
    """GEMINI_API_KEY(또는 GOOGLE_API_KEY)가 설정되어 있는지."""
    return bool(_api_key())


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
    """OpenAI 스타일 messages → (system_instruction, Gemini contents).

    - role 'system' → system_instruction 으로 합침
    - role 'assistant' → 'model', 'user' → 'user'
    """
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

    # Gemini는 첫 턴이 'user'여야 하므로 선행 'model' 턴(예: 환영 인사)을 제거
    while contents and contents[0]["role"] == "model":
        contents.pop(0)

    return "\n\n".join(system_parts), contents


def chat(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 500,
) -> str:
    """대화 메시지 리스트 → 어시스턴트 답변 텍스트."""
    from google.genai import types

    system_instruction, contents = _to_gemini(messages)
    config = types.GenerateContentConfig(
        system_instruction=system_instruction or None,
        temperature=temperature,
        max_output_tokens=max_tokens,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    resp = _client().models.generate_content(
        model=model or DEFAULT_CHAT_MODEL,
        contents=contents,
        config=config,
    )

    text = (resp.text or "").strip()
    if not text:
        candidates = getattr(resp, "candidates", None) or []
        finish_reason = candidates[0].finish_reason if candidates else "UNKNOWN"
        raise RuntimeError(f"empty response (finish_reason={finish_reason})")
    return text


def embed(
    texts: list[str],
    model: str | None = None,
    task_type: str = "RETRIEVAL_DOCUMENT",
) -> list[list[float]]:
    """텍스트 리스트 → 임베딩 벡터 리스트. (대량은 배치로 나눠 호출)"""
    from google.genai import types
    model = model or DEFAULT_EMBED_MODEL
    vectors: list[list[float]] = []
    batch_size = 100  # Gemini 임베딩 배치 상한 대비 보수적으로 설정
    for start in range(0, len(texts), batch_size):
        chunk = texts[start : start + batch_size]
        resp = _client().models.embed_content(
            model=model,
            contents=chunk,
            config=types.EmbedContentConfig(task_type=task_type),
        )
        vectors.extend(list(e.values) for e in resp.embeddings)
    return vectors
