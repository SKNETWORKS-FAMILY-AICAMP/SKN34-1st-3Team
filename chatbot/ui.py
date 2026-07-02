"""Streamlit 채팅 UI."""

from __future__ import annotations

import time

import streamlit as st

from chatbot import llm_client
from chatbot.intents import ChatContext, answer, classify_intent
from chatbot.prompts import WELCOME_MESSAGE

_EXAMPLE_QUESTIONS = [
    "전기차 보조금은 어떻게 받나요?",
    "가족용 전기 SUV 추천해줘",
    "서울 지역 Car-BTI 알려줘",
]
_COOLDOWN_SEC = 3


def _init_session():
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [
            {"role": "assistant", "content": WELCOME_MESSAGE},
        ]
    if "chat_last_sent_at" not in st.session_state:
        st.session_state.chat_last_sent_at = 0.0
    if "chat_diagnose_flow" not in st.session_state:
        st.session_state.chat_diagnose_flow = False
    if "chat_pending" not in st.session_state:
        st.session_state.chat_pending = None


def _in_diagnose_flow() -> bool:
    return bool(st.session_state.get("chat_diagnose_flow"))


def _spinner_label() -> str:
    if llm_client.is_available():
        return "🤖 AI가 답변을 생성하고 있습니다…"
    return "📋 관련 데이터를 검색해 답변을 준비하고 있습니다…"


def _process_pending(ctx: ChatContext) -> bool:
    """대기 중인 질문이 있으면 로딩 UI와 함께 답변 생성. 처리했으면 True."""
    pending = st.session_state.get("chat_pending")
    if not pending:
        return False

    with st.chat_message("assistant"):
        with st.status("답변 생성 중", expanded=True) as status:
            st.write("🔍 FAQ·차량·지역·뉴스 데이터 검색")
            status.update(label="✍️ 답변 작성 중", state="running")
            with st.spinner(_spinner_label()):
                reply = answer(
                    pending["query"],
                    ctx,
                    pending["history"],
                    in_diagnose_flow=pending.get("in_diagnose_flow", False),
                )
            status.update(label="✅ 답변 완료", state="complete")

        st.markdown(reply)

    st.session_state.chat_messages.append({"role": "assistant", "content": reply})
    st.session_state.chat_pending = None
    st.rerun()
    return True


def render_chatbot(ctx: ChatContext) -> None:
    _init_session()

    ai_on = llm_client.is_available()
    badge = "🟢 AI 모드" if ai_on else "🟡 기본 모드 (OPENAI_API_KEY 미설정)"
    st.caption(badge)

    if not ai_on:
        st.info(
            "`.env`에 `OPENAI_API_KEY`를 설정하면 AI 답변이 활성화됩니다. "
            "키가 없어도 FAQ·차량·뉴스는 규칙 기반으로 안내됩니다."
        )

    col_reset, _ = st.columns([1, 4])
    with col_reset:
        if st.button("🗑️ 대화 초기화", key="chat_reset"):
            st.session_state.chat_messages = [
                {"role": "assistant", "content": WELCOME_MESSAGE},
            ]
            st.session_state.chat_diagnose_flow = False
            st.session_state.chat_pending = None
            st.rerun()

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if _process_pending(ctx):
        return

    st.markdown("**예시 질문**")
    ex_cols = st.columns(len(_EXAMPLE_QUESTIONS))
    for i, q in enumerate(_EXAMPLE_QUESTIONS):
        if ex_cols[i].button(q, key=f"chat_example_{i}"):
            _queue_user_message(q, ctx)

    if prompt := st.chat_input("Car-BTI 관련 질문을 입력하세요"):
        _queue_user_message(prompt, ctx)


def _queue_user_message(prompt: str, ctx: ChatContext) -> None:
    now = time.monotonic()
    elapsed = now - st.session_state.chat_last_sent_at
    if elapsed < _COOLDOWN_SEC:
        st.warning(f"잠시 후 다시 시도해 주세요. ({_COOLDOWN_SEC - elapsed:.0f}초 대기)")
        return

    if st.session_state.get("chat_pending"):
        st.warning("이전 질문에 대한 답변을 생성 중입니다. 잠시만 기다려 주세요.")
        return

    st.session_state.chat_last_sent_at = now
    st.session_state.chat_messages.append({"role": "user", "content": prompt})

    intent = classify_intent(prompt)
    if intent == "diagnose":
        st.session_state.chat_diagnose_flow = True

    history = [
        m for m in st.session_state.chat_messages[:-1]
        if m["role"] in ("user", "assistant")
    ]
    st.session_state.chat_pending = {
        "query": prompt,
        "history": history,
        "in_diagnose_flow": _in_diagnose_flow(),
    }
    st.rerun()
