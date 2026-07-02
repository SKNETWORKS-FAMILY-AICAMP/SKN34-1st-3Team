from __future__ import annotations

import logging
import os
from typing import Any

from openai import OpenAI

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        # timeout으로 무한 대기 방지
        _client = OpenAI(timeout=15.0)
    return _client


def is_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def classify_db_related(query: str) -> bool | None:
    """
    LLM 분류 보조기.
    True/False 판단 불가 또는 실패 시 None 반환.
    """
    if not is_available():
        return None
    try:
        client = _get_client()
        resp = client.responses.create(
            model=os.getenv("OPENAI_CLASSIFIER_MODEL", "gpt-4o-mini"),
            input=[
                {
                    "role": "system",
                    "content": (
                        "너는 사용자의 질문이 자동차 DB 데이터(지역 통계/차량 추천/브랜드 FAQ)와 "
                        "직접 관련 있는지 분류한다. 관련 있으면 RELATED, 아니면 IRRELEVANT만 출력."
                    ),
                },
                {"role": "user", "content": query},
            ],
            temperature=0,
            max_output_tokens=5,
        )
        label = (resp.output_text or "").strip().upper()
        if "RELATED" in label and "IRRELEVANT" not in label:
            return True
        if "IRRELEVANT" in label:
            return False
        return None
    except Exception as exc:
        logger.warning("LLM 분류 실패: %s", type(exc).__name__)
        return None


def generate_answer(system_prompt: str, user_question: str, context_text: str) -> str:
    if not is_available():
        return (
            "OPENAI_API_KEY가 설정되지 않아 AI 응답을 생성할 수 없습니다. "
            "DB 조회 결과만 확인해 주세요."
        )

    client = _get_client()
    retries = int(os.getenv("OPENAI_MAX_RETRIES", "3"))
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            response = client.responses.create(
                model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
                input=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": (
                            f"[사용자 질문]\n{user_question}\n\n"
                            f"[DB 조회 컨텍스트]\n{context_text}\n\n"
                            "위 컨텍스트만 근거로 답변하세요."
                        ),
                    },
                ],
                temperature=0.2,
                max_output_tokens=int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "500")),
            )
            text = (response.output_text or "").strip()
            return text or "조회된 데이터가 없습니다."
        except Exception as exc:
            last_exc = exc
            logger.warning("LLM 생성 실패(%s/%s): %s", attempt + 1, retries, type(exc).__name__)
    raise RuntimeError(f"LLM 생성 실패: {last_exc}")
