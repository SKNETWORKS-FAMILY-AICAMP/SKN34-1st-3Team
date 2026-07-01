"""
chatbot 패키지
==============
Car-BTI 대시보드에 붙는 AI 상담 챗봇.

- llm_client : LLM/임베딩 호출 추상화 (Gemini, 키 없으면 폴백)
- retriever  : company_faq RAG 검색 (임베딩 ↔ 키워드 자동 전환)
- prompts    : 시스템 프롬프트
- intents    : 의도 분류 + [참고 자료] 조립 + 답변 생성
- ui         : Streamlit 챗봇 UI (render_chatbot)
"""

from .intents import ChatContext
from .ui import render_chatbot

__all__ = ["ChatContext", "render_chatbot"]
