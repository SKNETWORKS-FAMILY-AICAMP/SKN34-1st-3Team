"""
chatbot/ui.py
=============
Streamlit 챗봇 UI. app.py의 세 번째 탭에서 render_chatbot(ctx)를 호출한다.
"""

from __future__ import annotations

import streamlit as st

from . import llm_client
from .intents import ChatContext, answer

_SESSION_KEY = "chatbot_messages"

WELCOME = (
    "안녕하세요! 🚗 **Car-BTI AI 상담 도우미**예요.\n\n"
    "이런 걸 물어볼 수 있어요:\n"
    "- 🔧 브랜드/차량 FAQ (예: *전기차 보조금은 어떻게 받나요?*)\n"
    "- 🧪 내 성향 진단 (예: *내 Car-BTI 알려줘*)\n"
    "- 🚙 차량 추천 (예: *가족용 전기 SUV 추천해줘*)\n"
    "- 📰 최신 뉴스 (예: *현대 전기차 뉴스 알려줘*)"
)

SUGGESTIONS = [
    "전기차 보조금은 어떻게 받나요?",
    "내 Car-BTI 진단해줘",
    "도심용 가성비 국산차 추천해줘",
]


def _ensure_state() -> None:
    if _SESSION_KEY not in st.session_state:
        st.session_state[_SESSION_KEY] = [
            {"role": "assistant", "content": WELCOME}
        ]


def _send(prompt: str, ctx: ChatContext) -> None:
    history = st.session_state[_SESSION_KEY]
    with st.spinner("답변을 준비하고 있어요..."):
        reply = answer(prompt, history, ctx)
    history.append({"role": "user", "content": prompt})
    history.append({"role": "assistant", "content": reply})


def render_chatbot(ctx: ChatContext) -> None:
    _ensure_state()

    st.subheader("💬 Car-BTI AI 상담 챗봇")

    if llm_client.is_available():
        st.caption("🟢 AI 모드 (Gemini 연결됨) · FAQ·차량·지역 데이터를 근거로 답합니다.")
    else:
        st.caption(
            "🟡 기본 모드 · `GEMINI_API_KEY` 미설정 상태예요. "
            "FAQ 검색·차량 추천은 동작하며, 키를 설정하면 자연스러운 대화형 답변이 켜집니다."
        )

    # 초기화 버튼
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("🗑️ 대화 초기화", use_container_width=True):
            st.session_state[_SESSION_KEY] = [{"role": "assistant", "content": WELCOME}]
            st.rerun()

    # 지난 대화 표시
    for msg in st.session_state[_SESSION_KEY]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 추천 질문 버튼 (대화가 환영 메시지뿐일 때만)
    if len(st.session_state[_SESSION_KEY]) <= 1:
        st.write("💡 예시 질문:")
        cols = st.columns(len(SUGGESTIONS))
        for i, s in enumerate(SUGGESTIONS):
            with cols[i]:
                if st.button(s, key=f"sugg_{i}", use_container_width=True):
                    _send(s, ctx)
                    st.rerun()

    # 입력창
    if prompt := st.chat_input("무엇이든 물어보세요 (FAQ · 진단 · 추천 · 뉴스)"):
        _send(prompt, ctx)
        st.rerun()
