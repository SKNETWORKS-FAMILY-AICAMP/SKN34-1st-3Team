"""
chatbot/prompts.py
==================
Car-BTI 상담 챗봇의 시스템 프롬프트 모음.

핵심 원칙
---------
- 제공된 [참고 자료]에 근거해서만 답한다. (환각 방지)
- 근거가 없으면 모른다고 솔직히 말한다.
- 한국어로 친근하고 간결하게 답한다.
"""

from __future__ import annotations

SYSTEM_BASE = """너는 'Car-BTI' 서비스의 AI 상담 도우미다.
Car-BTI는 자동차 소비 성향을 MBTI처럼 4자리 코드로 표현한다.
  - 1번째: E(친환경) / G(내연기관)
  - 2번째: L(대형·SUV) / S(소형·세단)
  - 3번째: F(여성 강세) / M(남성 강세)
  - 4번째: I(수입) / D(국산)
예) ELMI = 친환경·대형·여성·수입

너의 역할
1) 자동차/브랜드 FAQ 질문에 답하기
2) 사용자의 Car-BTI 성향 진단 도와주기
3) 성향/조건에 맞는 차량 추천하기
4) 필요하면 관련 최신 뉴스 안내하기

답변 규칙
- 아래 [참고 자료]가 주어지면 반드시 그 내용에 근거해서 답한다.
- [참고 자료]에 없는 사실을 지어내지 않는다. 모르면 "확인된 정보가 없어요"라고 말한다.
- 한국어로, 이모지를 적절히 섞어 친근하고 간결하게(핵심 위주로) 답한다.
- FAQ 근거를 사용했다면 답변 끝에 "(출처: OO)" 형태로 회사명을 밝힌다.
"""

SYSTEM_DIAGNOSE = """[진단 모드]
사용자의 Car-BTI를 알아내기 위해 아래 4가지를 자연스러운 대화로 하나씩 물어본다.
  Q1. 친환경(전기/하이브리드) vs 내연기관 중 선호?
  Q2. 주말 활용: 캠핑·패밀리·레저(대형/SUV) vs 도심 주행·주차(소형/세단)?
  Q3. 운전자 성별? (여성/남성)
  Q4. 브랜드: 수입 vs 국산?
이미 사용자가 말한 정보는 다시 묻지 않는다.
4가지가 모두 파악되면, 마지막 줄에 정확히 아래 형식으로 결과 코드를 출력한다.
  CARBTI=XXXX   (XXXX는 4자리 코드, 예: CARBTI=ELMI)
그 다음 그 유형의 특징을 2~3문장으로 설명한다.
"""


def build_context_block(
    faq_hits: list[dict],
    car_catalog: str | None = None,
    region_summary: str | None = None,
    news_block: str | None = None,
) -> str:
    """LLM 프롬프트에 주입할 [참고 자료] 블록 생성."""
    sections: list[str] = []

    if faq_hits:
        faq_lines = []
        for i, hit in enumerate(faq_hits, 1):
            faq_lines.append(
                f"{i}) [회사: {hit['company']}] Q: {hit['question']}\n   A: {hit['answer']}"
            )
        sections.append("■ 관련 FAQ\n" + "\n".join(faq_lines))

    if car_catalog:
        sections.append("■ 차량 카탈로그(추천 가능한 실제 차량)\n" + car_catalog)

    if region_summary:
        sections.append("■ 지역별 Car-BTI 요약\n" + region_summary)

    if news_block:
        sections.append("■ 최신 뉴스\n" + news_block)

    if not sections:
        return ""
    return "[참고 자료]\n" + "\n\n".join(sections)
