from __future__ import annotations

import re

from chatbot.prompts import OUT_OF_SCOPE_MESSAGE

DB_RELATED_KEYWORDS = {
    "general": [
        "데이터", "db", "database", "통계", "수치", "비율", "등록", "분포", "지표", "추이", "증감", "평균", "상위", "top",
    ],
    "region_persona": [
        "지역", "시도", "서울", "부산", "인천", "대구", "광주", "대전", "울산", "세종", "경기", "강원",
        "충북", "충남", "전북", "전남", "경북", "경남", "제주", "car-bti", "페르소나", "mbti",
    ],
    "car_recommend": [
        "차량", "추천", "브랜드", "모델", "차종", "현대", "기아", "제네시스", "bmw", "벤츠", "수입차", "국산차",
    ],
    "faq": [
        "faq", "자주 묻는 질문", "질문", "답변", "충전", "보조금", "보험", "정비", "유지비", "서비스",
    ],
}


def is_greeting(text: str) -> bool:
    s = text.strip().lower()
    return s in {"안녕", "안녕하세요", "hi", "hello", "헬로", "반가워", "ㅎㅇ", "하이"}


def keyword_related(text: str) -> bool:
    s = text.lower()
    return any(k in s for group in DB_RELATED_KEYWORDS.values() for k in group)


def can_answer(text: str) -> bool:
    numeric_pattern = r"(상위|top|비율|건수|몇|얼마|증감|추이|평균|가장|많은|적은|동일|같은|똑같)"
    persona_pattern = r"(?<![A-Za-z])[EG][LS][FM][ID](?![A-Za-z])"
    return (
        keyword_related(text)
        or re.search(numeric_pattern, text.lower()) is not None
        or re.search(persona_pattern, text.upper()) is not None
    )


def intent_hints(text: str) -> set[str]:
    s = text.lower()
    hints: set[str] = set()
    if any(k in s for k in DB_RELATED_KEYWORDS["region_persona"]):
        hints.add("region_persona")
    if any(k in s for k in DB_RELATED_KEYWORDS["car_recommend"]):
        hints.add("car_recommend")
    if any(k in s for k in DB_RELATED_KEYWORDS["faq"]):
        hints.add("faq")
    if not hints and keyword_related(text):
        hints.add("general")
    return hints


def out_of_scope_message() -> str:
    return OUT_OF_SCOPE_MESSAGE
