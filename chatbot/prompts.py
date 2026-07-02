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

SYSTEM_BASE = """너는 'Car-BTI' AI 상담 도우미다.
Car-BTI: 자동차 소비 성향을 4자리 코드로 표현 (E/G · L/S · F/M · I/D)

아래 [참고 자료]에만 기반해 답한다. 근거 없으면 "확인된 정보가 없어요"라고 말한다.
한국어로 이모지를 섞어 간결하게(핵심 위주) 답하고, FAQ 근거 사용 시 "(출처: OO)"를 붙인다."""

SYSTEM_DIAGNOSE = """[진단 모드] 아래 4가지를 자연스럽게 물어보고, 모두 파악되면:
CARBTI=XXXX 형식으로 결과를 출력한 후 그 유형의 특징을 2문장으로 설명한다.
  Q1. 친환경 vs 내연기관?
  Q2. 대형/SUV vs 소형/세단?
  Q3. 운전자 성별?
  Q4. 수입 vs 국산?"""


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
