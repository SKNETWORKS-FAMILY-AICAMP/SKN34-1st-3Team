from __future__ import annotations

import re

# 페르소나 코드 → 지역 목록을 묻는 신호
REGION_LIST_SIGNALS = [
    "지역", "어디", "시도", "있어", "있나", "있니", "있을까", "해당",
    "맞는", "어느", "무슨 지역", "어떤 지역", "지역도", "지역은", "지역이",
    "목록", "리스트", "몇 개", "몇곳",
]

# 페르소나 상세(설명/키워드)를 묻는 신호 — 지역 질문보다 우선순위 낮음
DETAIL_SIGNALS = [
    "페르소나 설명", "유형 설명", "특징", "키워드", "뜻", "의미",
    "어떤 유형", "무슨 유형", "어떤 성향", "무슨 성향", "소개",
    "설명해", "뭐야", "무엇", "뭔지", "궁금해",
]

RECOMMEND_SIGNALS = ["추천", "차량 추천", "차 추천", "모델 추천", "어떤 차", "무슨 차"]

SAME_REGION_SIGNALS = ["같은", "동일", "똑같", "같아", "비슷한 지역"]


def asks_persona_region_list(query: str) -> bool:
    """페르소나 코드에 해당하는 지역 목록을 묻는지."""
    q = query.lower()
    if any(s in q for s in REGION_LIST_SIGNALS):
        return True
    if re.search(r"(같은|동일|똑같).{0,12}(지역|시도)", q):
        return True
    if re.search(r"(지역|시도).{0,12}(있|알려|어디)", q):
        return True
    return False


def asks_persona_detail(query: str) -> bool:
    """페르소나 유형 설명/키워드를 묻는지 (지역 질문이면 제외)."""
    if asks_persona_region_list(query):
        return False
    q = query.lower()
    if any(s in q for s in DETAIL_SIGNALS):
        return True
    # car-bti 코드만 언급하고 설명을 묻는 패턴: "ESFI가 뭐야"
    if ("car-bti" in q or "car bti" in q) and any(s in q for s in ["뭐", "무엇", "설명", "뜻"]):
        return True
    return False


def asks_car_recommendation(query: str) -> bool:
    if asks_persona_region_list(query):
        return False
    q = query.lower()
    return any(s in q for s in RECOMMEND_SIGNALS) or (
        "차량" in q and any(s in q for s in ["추천", "골라", "찾아", "알려"])
    )


def asks_region_car_bti(query: str, has_region: bool) -> bool:
    if not has_region:
        return False
    q = query.lower()
    return ("car-bti" in q) or ("car bti" in q) or ("페르소나" in q) or ("mbti" in q) or ("성향" in q)


def asks_same_persona_as_region(query: str, has_region: bool) -> bool:
    if not has_region:
        return False
    q = query.lower()
    if not any(s in q for s in SAME_REGION_SIGNALS):
        return False
    return ("car-bti" in q) or ("car bti" in q) or ("페르소나" in q) or asks_persona_region_list(query)
