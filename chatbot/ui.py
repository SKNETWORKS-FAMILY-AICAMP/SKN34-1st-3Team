from __future__ import annotations

import streamlit as st

from chatbot.embeddings import is_embedding_enabled
from chatbot.intents import ChatContext, answer, classify_intent
from chatbot.prompts import WELCOME_MESSAGE
from chatbot.vector_store import VectorIndex

_CHAT_STYLES = """
<style>
.chat-help-card {
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 12px 14px;
    background: #f8fafc;
    margin-bottom: 8px;
}
.chat-help-title { font-weight: 700; margin-bottom: 6px; }
.chat-help-item { color: #334155; font-size: 13px; margin-bottom: 2px; }

.chat-history-wrap {
    max-height: min(52vh, 520px);
    overflow-y: auto;
    padding: 8px 4px 12px;
    margin-bottom: 8px;
    border: 1px solid #e8edf3;
    border-radius: 14px;
    background: linear-gradient(180deg, #f8fafc 0%, #ffffff 100%);
}

.chat-bottom-bar {
    margin-top: 4px;
    padding-top: 8px;
    border-top: 1px solid #e8edf3;
}

/* 사용자: 오른쪽 파란 말풍선 */
div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
    flex-direction: row-reverse;
    background: transparent;
}
div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stChatMessageContent"] {
    background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
    color: #ffffff;
    border-radius: 18px 18px 4px 18px;
    padding: 12px 16px;
    border: none;
    box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
    max-width: 82%;
    margin-left: auto;
}
div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stChatMessageContent"] p,
div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stChatMessageContent"] li {
    color: #ffffff;
}

/* 봇: 왼쪽 회색 말풍선 */
div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
    background: transparent;
}
div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) [data-testid="stChatMessageContent"] {
    background: #f1f5f9;
    color: #0f172a;
    border-radius: 18px 18px 18px 4px;
    padding: 12px 16px;
    border: 1px solid #e2e8f0;
    box-shadow: 0 1px 4px rgba(15, 23, 42, 0.06);
    max-width: 88%;
}
div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) [data-testid="stChatMessageContent"] p,
div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) [data-testid="stChatMessageContent"] li {
    color: #0f172a;
}

.quick-chip button {
    font-size: 12px !important;
    border-radius: 20px !important;
    border: 1px solid #cbd5e1 !important;
    background: #ffffff !important;
    color: #334155 !important;
    min-height: 2rem !important;
}
.quick-chip button:hover {
    border-color: #2563eb !important;
    color: #1d4ed8 !important;
    background: #eff6ff !important;
}
</style>
"""


def render_chatbot(ctx: ChatContext) -> None:
    st.markdown(_CHAT_STYLES, unsafe_allow_html=True)

    st.subheader("💬 DB 기반 AI 상담 챗봇")
    st.caption("지역·Car-BTI·추천차량·FAQ 데이터를 기반으로 답변합니다.")

    _render_vector_status(ctx)
    _init_chat_state()
    _render_help_card()
    _render_quick_buttons()

    # ── 대화 기록 (스크롤, 아래로 쌓임) ──
    history = st.container()
    with history:
        st.markdown('<div class="chat-history-wrap">', unsafe_allow_html=True)
        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"].replace("\n", "  \n"))

        if st.session_state.get("_chat_pending_user"):
            user_q = st.session_state.pop("_chat_pending_user")
            with st.chat_message("assistant"):
                with st.spinner("답변 생성 중..."):
                    reply = answer(user_q, ctx)
                st.markdown(reply.replace("\n", "  \n"))
            st.session_state.chat_messages.append({"role": "assistant", "content": reply})
            st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    # ── 하단 고정: 입력창 → 액션 버튼 ──
    st.markdown('<div class="chat-bottom-bar">', unsafe_allow_html=True)

    with st.form("chat_input_form", clear_on_submit=True):
        input_col, btn_col = st.columns([6, 1], gap="small")
        with input_col:
            prompt = st.text_input(
                "질문 입력",
                placeholder="질문을 입력하세요. 예: 2026-05 부산과 같은 Car-BTI 지역은?",
                label_visibility="collapsed",
                key="chat_prompt_field",
            )
        with btn_col:
            submitted = st.form_submit_button("전송", use_container_width=True)

    pending_quick = st.session_state.pop("chat_quick_prompt", None)
    candidate = (prompt.strip() if submitted and prompt else None) or pending_quick

    if candidate:
        _enqueue_user_message(candidate, ctx)

    col1, col2 = st.columns([1, 1], gap="small")
    with col1:
        if st.button("대화 초기화", use_container_width=True, key="chat_reset_btn"):
            st.session_state.chat_messages = [{"role": "assistant", "content": WELCOME_MESSAGE}]
            st.session_state.chat_last_intent = "none"
            st.session_state.pop("_chat_pending_user", None)
            st.session_state.pop("chat_quick_prompt", None)
            st.rerun()
    with col2:
        st.button(
            "DB 질문 가이드",
            disabled=True,
            use_container_width=True,
            key="chat_guide_btn",
            help="지역+월+의도를 함께 질문할수록 정확도가 높습니다.",
        )

    st.markdown("</div>", unsafe_allow_html=True)


def _init_chat_state() -> None:
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [{"role": "assistant", "content": WELCOME_MESSAGE}]
    if "chat_last_intent" not in st.session_state:
        st.session_state.chat_last_intent = "none"


def _enqueue_user_message(prompt: str, ctx: ChatContext) -> None:
    clean = prompt.strip()
    if not clean:
        return
    st.session_state.chat_last_intent = classify_intent(clean, ctx)
    st.session_state.chat_messages.append({"role": "user", "content": clean})
    st.session_state._chat_pending_user = clean
    st.rerun()


def _render_vector_status(ctx: ChatContext) -> None:
    status = (
        ctx.vector_index.get_status()
        if ctx.vector_index is not None
        else {"embedding_enabled": is_embedding_enabled()}
    )
    if status.get("embedding_enabled") and status.get("faq_count", 0) > 0:
        st.success(
            f"의미 기반 검색 활성화 ({status.get('embedding_provider', '?')}) · "
            f"FAQ {status.get('faq_count', 0)}건 · 페르소나 {status.get('persona_count', 0)}건"
        )
    elif is_embedding_enabled():
        st.warning(
            "Vector 인덱스가 비어 있습니다. `python sync_vector_index.py --force` 실행이 필요합니다."
        )
    else:
        st.info("키워드 검색 모드입니다.")


def _render_help_card() -> None:
    st.markdown(
        """
        <div class="chat-help-card">
          <div class="chat-help-title">빠른 질문 예시</div>
          <div class="chat-help-item">• 2026-05 서울의 Car-BTI 알려줘</div>
          <div class="chat-help-item">• ELMI 유형과 같은 지역은 어디야?</div>
          <div class="chat-help-item">• ESFI 추천 차량과 이유 알려줘</div>
          <div class="chat-help-item">• 현대 충전 관련 FAQ 요약해줘</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_quick_buttons() -> None:
    samples = [
        "서울의 최근 car-bti는 뭐야?",
        "2026-05 부산과 같은 car-bti 지역은?",
        "ELFI 추천 차량 알려줘",
        "기아 전기차 FAQ 알려줘",
    ]
    quick_cols = st.columns(4)
    for i, col in enumerate(quick_cols):
        with col:
            st.markdown('<div class="quick-chip">', unsafe_allow_html=True)
            if st.button(samples[i], use_container_width=True, key=f"quick_q_{i}"):
                st.session_state["chat_quick_prompt"] = samples[i]
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
