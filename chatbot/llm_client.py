"""OpenAI Chat API 클라이언트 (스로틀·재시도·잘림 방지 포함)."""

from __future__ import annotations

import os
import time

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

try:
    from openai import APIStatusError, OpenAI, RateLimitError
except ImportError:
    OpenAI = None  # type: ignore
    APIStatusError = Exception  # type: ignore
    RateLimitError = Exception  # type: ignore

_last_request_at: float = 0.0
_CONTINUE_HINT = (
    "이전 답변이 출력 제한으로 중간에 끊겼습니다. "
    "끊긴 부분부터 이어서 완결된 문장으로만 마무리해 주세요. 이미 쓴 내용은 반복하지 마세요."
)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def is_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY")) and OpenAI is not None


def get_model() -> str:
    return os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")


def _throttle() -> None:
    global _last_request_at
    interval = _env_float("OPENAI_MIN_REQUEST_INTERVAL", 2.0)
    elapsed = time.monotonic() - _last_request_at
    if elapsed < interval:
        time.sleep(interval - elapsed)


def chat_completion(
    messages: list[dict[str, str]],
    *,
    max_tokens: int | None = None,
) -> str:
    """OpenAI chat.completions 호출. length 잘림 시 자동 이어쓰기."""
    if not is_available():
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = get_model()
    max_out = max_tokens or _env_int("OPENAI_MAX_OUTPUT_TOKENS", 2048)
    max_retries = _env_int("OPENAI_MAX_RETRIES", 3)
    max_continuations = _env_int("OPENAI_MAX_CONTINUATIONS", 2)

    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            _throttle()
            content = _complete_with_continuation(
                client, model, messages, max_out, max_continuations,
            )
            global _last_request_at
            _last_request_at = time.monotonic()
            return content
        except RateLimitError as exc:
            last_err = exc
            time.sleep(2 ** attempt)
        except APIStatusError as exc:
            if exc.status_code == 429:
                last_err = exc
                time.sleep(2 ** attempt)
                continue
            raise
        except Exception as exc:
            last_err = exc
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

    raise RuntimeError(f"OpenAI API 호출 실패: {last_err}")


def _complete_with_continuation(
    client: OpenAI,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    max_continuations: int,
) -> str:
    """finish_reason=length 이면 이어쓰기로 문장 잘림 방지."""
    parts: list[str] = []
    current = list(messages)

    for _ in range(max_continuations + 1):
        resp = client.chat.completions.create(
            model=model,
            messages=current,  # type: ignore[arg-type]
            max_tokens=max_tokens,
            temperature=0.4,
        )
        chunk = (resp.choices[0].message.content or "").strip()
        if chunk:
            parts.append(chunk)
        if resp.choices[0].finish_reason != "length":
            break
        current = current + [
            {"role": "assistant", "content": chunk},
            {"role": "user", "content": _CONTINUE_HINT},
        ]

    return "\n".join(parts).strip()
