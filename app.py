"""
app.py
======
전국 Car-BTI 대시보드 (v4 - 16종 MBTI 1:1 맞춤형 연동)

기능 요약
---------
[Tab 1] 🗺️ 지역 분석
  ① 지도 시각화 4축 토글 (전기차/SUV/성별/수입차)
  ② 16색 페르소나 모드
  ③ 레이더 차트로 선택 지역의 4축 점수 한눈에
  ④ 16종 페르소나 1:1 매칭 차량 프로필 카드
  ⑤ 맞춤형 FAQ 큐레이션

[Tab 2] 🧪 나의 Car-BTI 테스트
  4문항 설문 → 본인 페르소나 산출
  → 가장 비슷한 지역 Top 3 / 매칭 차량 / 맞춤 FAQ Top 3
"""

import io
import os

import folium
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from streamlit_folium import st_folium

from db_config import get_engine
from news_api import build_news_query, fetch_naver_news, has_naver_news_keys
from chatbot import ChatContext, render_chatbot

# ════════════════════════════════════════
# 페이지 설정 & 상수
# ════════════════════════════════════════
st.set_page_config(page_title="전국 Car-BTI 대시보드", page_icon="🗺️", layout="wide")

# ════════════════════════════════════════
# 전체 배경 (콘텐츠 가독성 우선)
# ════════════════════════════════════════
st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(135deg, #f0fdf4 0%, #eff6ff 100%) !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# region_stats(MySQL)의 짧은 시도명 ↔ geojson 의 정식 시도명 매핑
REGION_FULL_MAP = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시",
    "인천": "인천광역시", "광주": "광주광역시", "대전": "대전광역시",
    "울산": "울산광역시", "세종": "세종특별자치시", "경기": "경기도",
    "강원": "강원도", "충북": "충청북도", "충남": "충청남도",
    "전북": "전라북도", "전남": "전라남도", "경북": "경상북도",
    "경남": "경상남도", "제주": "제주특별자치도",
}

AXIS_LABELS = {
    "E": ("⚡", "친환경 (Eco)"),
    "G": ("⛽", "내연기관 (Gasoline)"),
    "L": ("🏕️", "대형 (Large)"),
    "S": ("🏙️", "소형 (Small)"),
    "F": ("👩", "여성 강세 (Female)"),
    "M": ("👨", "남성 강세 (Male)"),
    "I": ("🌍", "수입 (Import)"),
    "D": ("🇰🇷", "국산 (Domestic)"),
}

AXIS_DESC = {
    "E": "전기차 등 친환경 차량 보급률이 높고 인프라가 잘 갖춰진 지역",
    "G": "내연기관 차량의 비중이 높고 익숙함을 선호하는 지역",
    "L": "험지/캠핑/다목적 공간을 위한 SUV·대형차 선호도가 높은 지역",
    "S": "주차와 도심 주행에 유리한 세단·중소형차를 선호하는 지역",
    "F": "여성 명의 차량 등록 비율이 전국 평균보다 높은 지역",
    "M": "남성 명의 차량 등록 비율이 전국 평균보다 높은 지역",
    "I": "해외 브랜드 차량 등록 비중이 높은 지역",
    "D": "현대·기아 등 국산 브랜드 비중이 높은 실용적 지역",
}

PERSONA_COLORS = {
    "ESMD": "#a7f3d0", "ESMI": "#6ee7b7", "ESFD": "#34d399", "ESFI": "#10b981",
    "ELMD": "#bbf7d0", "ELMI": "#86efac", "ELFD": "#22c55e", "ELFI": "#15803d",
    "GSMD": "#fed7aa", "GSMI": "#fdba74", "GSFD": "#fb923c", "GSFI": "#f97316",
    "GLMD": "#fecaca", "GLMI": "#fca5a5", "GLFD": "#f87171", "GLFI": "#dc2626",
}

PERSONA_NICKNAMES = {
    # ─── 친환경 + 소형 (도심 EV형) ───
    "ESMD": ("⚡ 도시형 얼리어답터",
             "충전 인프라가 잘 갖춰진 도심에서 컴팩트 EV로 합리적 친환경 라이프를 즐기는 1·2인 가구 남성"),
    "ESMI": ("🌟 테크 마니아",
             "최신 수입 EV의 성능과 기술에 진심인, 도심 출퇴근과 드라이브를 즐기는 얼리어답터"),
    "ESFD": ("🌱 스마트 친환경 시티즌",
             "유지비 부담 없이 도심을 누비는 합리적 국산 EV로 환경과 일상을 모두 챙기는 여성 운전자"),
    "ESFI": ("✨ 그린 라이프스타일러",
             "감각적인 수입 EV로 도시 라이프와 친환경 가치관을 동시에 표현하는 트렌드 세터"),
    
    # ─── 친환경 + 대형 (패밀리 EV형) ───
    "ELMD": ("🏔️ 그린 패밀리 가장",
             "넓은 실내와 긴 주행거리를 갖춘 국산 대형 EV로 가족과 함께 레저·캠핑을 즐기는 패밀리 헤드"),
    "ELMI": ("👑 럭셔리 EV 컬렉터",
             "프리미엄 수입 대형 EV로 가족 이동·비즈니스·취미 활동까지 완벽하게 커버하는 고소득층"),
    "ELFD": ("🌳 친환경 패밀리 큐레이터",
             "안전과 편의성을 중시하며, 가족 모두가 만족하는 국산 대형 EV로 일상을 디자인하는 어머니"),
    "ELFI": ("💎 럭셔리 안전 패밀리",
             "스칸디 디자인의 안전한 수입 EV SUV로 가족의 가치와 환경 의식을 함께 추구하는 프리미엄 가족"),
    
    # ─── 내연 + 소형 (도심 가성비형) ───
    "GSMD": ("🛣️ 실용주의 시티 드라이버",
             "검증된 국산 세단·준중형으로 출퇴근과 도심 주행을 효율적으로 해결하는 합리적 남성"),
    "GSMI": ("🎯 도심형 수입 세단 마니아",
             "BMW 3시리즈·벤츠 C클래스 같은 클래식한 수입 세단으로 드라이빙의 즐거움을 추구하는 남성"),
    "GSFD": ("🍃 알뜰 첫차 드라이버",
             "유지비 부담 없는 국산 경차·준중형으로 안전한 도심 주행을 즐기는 여성 첫차 운전자"),
    "GSFI": ("👜 스타일 시티 드라이버",
             "미니·A클래스 같은 감각적인 수입 소형차로 도심 라이프스타일을 표현하는 트렌디한 여성"),
    
    # ─── 내연 + 대형 (패밀리·레저형) ───
    "GLMD": ("🏕️ 캠퍼 패밀리 가장",
             "팰리세이드·쏘렌토 같은 국산 대형 SUV로 캠핑과 레저, 패밀리 이동까지 책임지는 활동적 가장"),
    "GLMI": ("🏆 프리미엄 SUV 컬렉터",
             "BMW X5·벤츠 GLE 같은 럭셔리 수입 대형 SUV로 위상과 라이프스타일을 함께 표현하는 고소득층"),
    "GLFD": ("🚌 패밀리 미니밴 마스터",
             "카니발·스타리아·팰리세이드 같은 다인승 국산 차량으로 대가족의 일상을 든든하게 지키는 어머니"),
    "GLFI": ("🌸 럭셔리 안전 패밀리",
             "볼보 XC60·벤츠 GLC 같은 안전한 수입 중대형 SUV로 가족의 격조와 안전을 모두 챙기는 우아한 어머니"),
}

VIZ_MODES = {
    "⚡ 친환경 차량 비율": ("eco_ratio", "YlGn", "친환경 차량 비율 (%)"),
    "🚙 대형 승용차 비율": ("large_ratio", "Oranges", "대형 승용차 비율 (%)"),
    "👩 여성 등록 비율": ("female_ratio", "Purples", "여성 등록 비율 (%)"),
    "🌍 수입차 비중": ("import_ratio", "Blues", "수입차 비율 (%)"),
    "🌈 16색 페르소나": (None, None, None),
}


# ════════════════════════════════════════
# 데이터 로딩
# ════════════════════════════════════════
@st.cache_data
def load_geojson():
    geojson_url = (
        "https://raw.githubusercontent.com/southkorea/southkorea-maps/"
        "master/kostat/2013/json/skorea_provinces_geo_simple.json"
    )
    return requests.get(geojson_url).json()


@st.cache_data(ttl=300)
def load_region_stats():
    """MySQL `region_stats`(prepare_data.py+load_to_mysql.py 적재)에서 17개 시도 데이터 로드.

    팀 저장소 스키마: region(짧은 시도명), eco_ratio, large_ratio,
    female_ratio, import_ratio, persona_code(4자리 [E/G][L/S][F/M][I/D]) 등.
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            df = pd.read_sql("SELECT * FROM region_stats ORDER BY region", conn)
    except Exception as exc:
        st.error(f"❌ region_stats 로드 실패: {exc}")
        st.info(
            "→ `python prepare_data.py` 후 `python load_to_mysql.py` 를 먼저 실행해 "
            "region_stats 를 적재하세요."
        )
        st.stop()

    if df.empty:
        st.error("❌ region_stats 가 비어 있습니다.")
        st.info("→ `python prepare_data.py` → `python load_to_mysql.py` 를 실행하세요.")
        st.stop()

    df["region_full"] = df["region"].map(REGION_FULL_MAP).fillna(df["region"])
    return df


@st.cache_data(ttl=300)
def load_db():
    """MySQL에서 FAQ + 추천 차량 로드. 실패 시 빈 DF."""
    try:
        engine = get_engine()
    except Exception as exc:
        st.error(f"❌ MySQL 연결 실패: {exc}")
        return pd.DataFrame(), pd.DataFrame()

    try:
        with engine.connect() as conn:
            try:
                faq = pd.read_sql("SELECT * FROM company_faq", conn)
            except Exception:
                faq = pd.DataFrame()
            try:
                # 이미지 바이너리는 무거우므로 별도 조회 (목록은 메타데이터만)
                cars = pd.read_sql(
                    "SELECT car_id, persona_code, brand, car_model, price, reason, "
                    "img_url, img_mime FROM persona_cars",
                    conn,
                )
            except Exception:
                cars = pd.DataFrame()
        return faq, cars
    except Exception as exc:
        st.error(f"❌ MySQL 조회 실패: {exc}")
        return pd.DataFrame(), pd.DataFrame()


@st.cache_data(ttl=300)
def load_car_image(car_id: int):
    """persona_cars.img_data(LONGBLOB)에서 이미지 바이너리 로드."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            df = pd.read_sql(
                "SELECT img_data FROM persona_cars WHERE car_id = %(cid)s",
                conn,
                params={"cid": int(car_id)},
            )
        if df.empty:
            return None
        blob = df.iloc[0]["img_data"]
        if blob is None:
            return None
        return bytes(blob)
    except Exception:
        return None

@st.cache_data(ttl=1800, show_spinner=False)
def load_news_articles(query: str, display: int = 6):
    """네이버 뉴스 API 결과를 30분 동안 캐시."""
    try:
        return fetch_naver_news(query=query, display=display, sort="date")
    except Exception:
        return []


def _chatbot_news_fn(query: str, display: int = 5):
    """챗봇용 뉴스 조회 (캐시 우회 — 짧은 display)."""
    try:
        return fetch_naver_news(query=query, display=display, sort="date")
    except Exception:
        return []


geojson_data = load_geojson()
df_stats = load_region_stats()
faq_df, cars_df = load_db()


# ════════════════════════════════════════
# 유틸리티
# ════════════════════════════════════════
def match_score(persona: str, tags: str) -> float:
    """페르소나 ↔ FAQ 태그 매칭도 (베이스라인 + 직접 매칭)."""
    BASE = 0.15
    if not tags or pd.isna(tags):
        return BASE
    p_set = set(persona)
    t_set = {t.strip() for t in tags.split(",")}
    overlap = len(p_set & t_set)
    return min(BASE + overlap * 0.25, 1.0)


def overlap_chars(persona: str, tags: str) -> str:
    if not tags or pd.isna(tags):
        return ""
    return ",".join(sorted(set(persona) & {t.strip() for t in tags.split(",")}))


def get_recommended_cars(persona: str, cars: pd.DataFrame) -> pd.DataFrame:
    """새로운 DB 스키마(mbti 컬럼)에 맞춰 1:1 매칭 차량 반환."""
    if cars.empty:
        return pd.DataFrame()
    if "mbti" in cars.columns:
        matched = cars[cars["mbti"] == persona]
        if not matched.empty:
            return matched
    # 하위 호환성 유지
    if "persona_code" in cars.columns:
        matched = cars[cars["persona_code"] == persona]
        if not matched.empty:
            return matched.head(4)
    return pd.DataFrame()


def get_recommended_brands(persona: str, cars: pd.DataFrame) -> list[str]:
    rec = get_recommended_cars(persona, cars)
    if rec.empty or "brand" not in rec.columns:
        return []
    return rec["brand"].dropna().unique().tolist()


def make_radar(region: str, row) -> go.Figure:
    """4축 점수 레이더 차트 (실제 데이터 분포를 0~100으로 정규화)."""
    eco    = max(0, min((row["eco_ratio"]    - 8)  / 17 * 100, 100))
    large  = max(0, min((row["large_ratio"]  - 12) / 6  * 100, 100))
    female = max(0, min((row["female_ratio"] - 22) / 12 * 100, 100))
    imp    = max(0, min((row["import_ratio"] - 5)  / 20 * 100, 100))

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=[eco, large, female, imp, eco],
        theta=["⚡친환경", "🚙대형/SUV", "👩여성비율", "🌍수입차", "⚡친환경"],
        fill="toself",
        name=region,
        line_color="#3b82f6",
        fillcolor="rgba(59, 130, 246, 0.25)",
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], showticklabels=False),
            angularaxis=dict(tickfont=dict(size=13)),
        ),
        showlegend=False,
        height=320,
        margin=dict(t=20, b=20, l=40, r=40),
    )
    return fig


def persona_desc_html(persona: str) -> str:
    parts = []
    for c in persona:
        emoji, label = AXIS_LABELS[c]
        parts.append(f"{emoji} <b>{label}</b> — {AXIS_DESC[c]}<br>")
    return "".join(parts)


def render_recommended_cars(persona: str, cars: pd.DataFrame):
    """단일 차량 프로필 카드 UI."""
    if cars.empty:
        st.warning("⚠️ 차량 DB(persona_cars)가 비어있습니다. 크롤러 스크립트를 먼저 실행해주세요.")
        return

    rec = get_recommended_cars(persona, cars)
    if rec.empty:
        st.warning(f"⚠️ [{persona}] 유형에 매칭된 차량이 없습니다.")
        return

    st.caption(
        f"**{persona}** = "
        + " · ".join(f"{AXIS_LABELS[c][0]} {AXIS_LABELS[c][1]}" for c in persona)
        + " 에 완벽하게 매칭된 대표 차량"
    )

    for i, (_, car) in enumerate(rec.iterrows()):
        with st.container(border=True):
            col1, col2 = st.columns([1, 2], gap="large")
            
            with col1:
                img_bytes = None
                car_id = car.get("car_id")
                if pd.notna(car_id):
                    img_bytes = load_car_image(int(car_id))

                img_path = car.get("img_url")
                if img_bytes:
                    st.image(io.BytesIO(img_bytes), use_column_width=True)
                elif img_path and isinstance(img_path, str) and os.path.exists(img_path):
                    st.image(img_path, use_column_width=True)
                else:
                    st.markdown(
                        "<div style='height:200px;background:#f0f4f8;border-radius:8px;"
                        "display:flex;align-items:center;justify-content:center;color:#64748b;"
                        "font-size:13px;text-align:center;padding:12px'>"
                        "🚗<br/><span style=\"font-size:11px\">이미지를 불러올 수 없습니다.</span>"
                        "</div>",
                        unsafe_allow_html=True,
                    )
            
            with col2:
                st.subheader(f"{car['brand']} {car['car_model']}")
                
                # 구 스키마 컬럼 예외 처리
                price = car.get("price")
                if pd.notna(price) and price:
                    st.caption(f"💸 예상 가격: {price}")
                    
                reason = car.get("reason")
                if pd.notna(reason) and reason:
                    st.write(reason)
                    
                st.markdown(f"✨ **사용자의 [{persona}] 성향에 기반하여 1:1로 큐레이팅된 모델입니다.**")
                st.markdown("차량과 관련된 세부적인 정보나 유지 관리 팁은 하단의 FAQ를 확인해 보세요.")

def render_news_section(persona: str, cars: pd.DataFrame, title: str = "최신 자동차 뉴스"):
    """추천 차량/브랜드 기반 최신 뉴스 섹션."""
    rec = get_recommended_cars(persona, cars)

    brands: list[str] = []
    models: list[str] = []

    if not rec.empty:
        if "brand" in rec.columns:
            brands = rec["brand"].dropna().astype(str).unique().tolist()
        if "car_model" in rec.columns:
            models = rec["car_model"].dropna().astype(str).head(2).tolist()

    query = build_news_query(brands=brands, car_models=models)

    st.subheader(title)

    if not has_naver_news_keys():
        st.info(
            "네이버 뉴스 API 키가 아직 설정되지 않았습니다. "
            ".env 파일에 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET을 추가하면 최신 뉴스가 표시됩니다."
        )
        return

    articles = load_news_articles(query, display=6)

    st.caption(f"뉴스 검색어: {query}")

    if not articles:
        st.info("현재 불러올 수 있는 뉴스가 없습니다. API 키, 검색 API 권한, 네트워크 상태를 확인해 주세요.")
        return

    for article in articles:
        with st.container(border=True):
            st.markdown(f"**[{article['title']}]({article['link']})**")
            if article.get("published_at"):
                st.caption(article["published_at"])
            if article.get("description"):
                st.write(article["description"])


def render_faq_list(
    persona: str,
    faq: pd.DataFrame,
    cars: pd.DataFrame,
    top_n: int = None,
):
    if faq.empty:
        st.warning("⚠️ FAQ 데이터가 비어있습니다. 크롤러를 다시 실행해주세요.")
        return

    brands = get_recommended_brands(persona, cars)

    scored = faq.copy()
    if "persona_tags" in scored.columns:
        scored["_score"] = scored["persona_tags"].apply(lambda t: match_score(persona, t))
        scored["_overlap"] = scored["persona_tags"].apply(lambda t: overlap_chars(persona, t))
    else:
        scored["_score"] = 0.15
        scored["_overlap"] = ""

    # ── 추천 차량에 해당하는 "기업의 FAQ"만 노출 ──
    if "company" in scored.columns and brands:
        is_brand = scored["company"].isin(brands)
        # K Car 옥션 FAQ는 페르소나와 3자리 이상 일치할 때만 보조 노출
        is_custom_match = scored.apply(
            lambda r: ("K Car" in str(r["company"]))
            and len(str(r["_overlap"]).split(",")) >= 3,
            axis=1,
        )
        filtered = scored[is_brand | is_custom_match]
        if not filtered.empty:
            scored = filtered

        # 추천 기업별 라운드로빈 정렬: 각 기업(예: 현대·기아·제네시스) FAQ가
        # 점수가 높은 시드에 묻히지 않고 고르게 상위 노출되도록 한다.
        brand_mask = scored["company"].isin(brands)
        bdf = scored[brand_mask].copy()
        if not bdf.empty:
            bdf["_rank"] = (
                bdf.groupby("company")["_score"]
                .rank(method="first", ascending=False)
            )
            bdf = bdf.sort_values(["_rank", "_score"], ascending=[True, False])
        cdf = scored[~brand_mask].sort_values("_score", ascending=False)
        scored = pd.concat([bdf, cdf])
        if brands:
            st.caption(
                "추천 차량 브랜드 **"
                + " · ".join(brands)
                + "** 의 FAQ를 우선 보여드립니다."
            )
    else:
        scored = scored.sort_values("_score", ascending=False)

    if top_n:
        scored = scored.head(top_n)

    if scored.empty:
        st.info("해당 성향에 매칭되는 FAQ가 없습니다.")
        return

    for _, row in scored.iterrows():
        pct = int(row["_score"] * 100)
        ov = row["_overlap"]
        company = row.get("company", "")
        badge = f"🎯 매칭 {pct}%"
        if company:
            badge = f"💬 {company} · {badge}"
        if ov:
            badge += f" · 일치: {ov}"
        
        with st.expander(f"{badge}  |  Q. {row['question']}"):
            st.progress(row["_score"], text=f"페르소나 [{persona}] 매칭도")
            st.write(row["answer"])
            cat = row.get("car_category", "")
            tags = row.get("persona_tags", "")
            st.caption(f"카테고리: {cat} · 페르소나 태그: {tags}")


# ════════════════════════════════════════
# 세션 상태
# ════════════════════════════════════════
if "selected_region" not in st.session_state:
    st.session_state.selected_region = "서울"


def on_region_input():
    user_input = st.session_state.get("region_input", "").strip()
    if not user_input:
        return
    for r in df_stats["region"].values:
        if user_input[:2] in r:
            st.session_state.selected_region = r
            return


# ════════════════════════════════════════
# 헤더 & 탭
# ════════════════════════════════════════
st.markdown(
    """
    <style>
    .hero-banner {
        background-image:
            linear-gradient(rgba(15, 23, 42, 0.55), rgba(15, 23, 42, 0.65)),
            url('https://images.unsplash.com/photo-1493238792000-8113da705763?auto=format&fit=crop&w=1920&q=80');
        background-size: cover;
        background-position: center;
        border-radius: 14px;
        padding: 42px 36px;
        margin-bottom: 8px;
    }
    .hero-banner h1 {
        color: #ffffff;
        font-size: 34px;
        font-weight: 800;
        margin: 0 0 10px 0;
    }
    .hero-banner p {
        color: #e5e7eb;
        font-size: 15px;
        margin: 0;
    }
    </style>
    <div class="hero-banner">
        <h1>🗺️ 전국 지역별 자동차 소비 성향 (Car-BTI) 분석</h1>
        <p>지도를 클릭하거나 지역명을 입력해 4자리 Car-BTI를 확인해보세요.
        두 번째 탭에서는 나만의 Car-BTI를 직접 진단하고,
        세 번째 탭에서 AI 상담 챗봇과 대화할 수 있습니다.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.expander("🧬 Car-BTI 가 처음이신가요? — 4가지 축 설명 보기", expanded=False):
    st.markdown(
        "Car-BTI는 **MBTI 처럼 4가지 축의 조합 (총 16가지 유형)** 으로 자동차 소비 성향을 표현합니다. "
        "각 자리수는 서로 반대되는 성향 중 하나를 나타냅니다."
    )
    axis_cols = st.columns(4)
    axis_pairs = [
        ("⚡", "E", "친환경",     "⛽", "G", "내연기관"),
        ("🏕️", "L", "대형/SUV",  "🏙️", "S", "소형/세단"),
        ("👩", "F", "여성 강세",  "👨", "M", "남성 강세"),
        ("🌍", "I", "수입",       "🇰🇷", "D", "국산"),
    ]
    for i, (e1, c1, l1, e2, c2, l2) in enumerate(axis_pairs):
        with axis_cols[i]:
            st.markdown(
                f"<div style='border:1px solid #e2e8f0;border-radius:8px;padding:14px;text-align:center;background:#f8fafc'>"
                f"<div style='font-size:22px'>{e1}</div>"
                f"<div style='font-weight:bold;font-size:18px;font-family:monospace'>{c1}</div>"
                f"<div style='color:#475569;font-size:13px;margin-bottom:8px'>{l1}</div>"
                f"<div style='color:#94a3b8;font-size:18px;margin:4px 0'>↕</div>"
                f"<div style='color:#475569;font-size:13px;margin-top:8px'>{l2}</div>"
                f"<div style='font-weight:bold;font-size:18px;font-family:monospace'>{c2}</div>"
                f"<div style='font-size:22px'>{e2}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

st.divider()

tab1, tab2, tab3 = st.tabs(
    ["🗺️ 지역 분석", "🧪 나의 Car-BTI 테스트", "💬 AI 상담"]
)

# ════════════════════════════════════════
# Tab 1: 지역 분석
# ════════════════════════════════════════
with tab1:
    viz_mode = st.radio(
        "🎨 지도 시각화 기준",
        list(VIZ_MODES.keys()),
        horizontal=True,
        key="viz_mode",
    )

    col_map, col_info = st.columns([5, 5])

    with col_map:
        st.subheader("📍 전국 Car-BTI 지도")

        m = folium.Map(location=[36.5, 127.5], zoom_start=7, tiles="CartoDB positron")
        col, palette, label = VIZ_MODES[viz_mode]

        if col is None:
            persona_map = dict(zip(df_stats["region_full"], df_stats["persona_code"]))

            def style_fn(feature):
                name = feature["properties"]["name"]
                p = None
                for r, pp in persona_map.items():
                    if r.startswith(name[:2]) or name.startswith(r[:2]):
                        p = pp
                        break
                color = PERSONA_COLORS.get(p, "#cccccc")
                return {"fillColor": color, "fillOpacity": 0.75, "color": "#666", "weight": 1}

            folium.features.GeoJson(
                geojson_data,
                style_function=style_fn,
                tooltip=folium.features.GeoJsonTooltip(fields=["name"], aliases=["지역:"]),
            ).add_to(m)
        else:
            folium.Choropleth(
                geo_data=geojson_data,
                data=df_stats,
                columns=["region_full", col],
                key_on="feature.properties.name",
                fill_color=palette,
                fill_opacity=0.7,
                line_opacity=0.3,
                legend_name=label,
            ).add_to(m)
            folium.features.GeoJson(
                geojson_data,
                style_function=lambda x: {"fillColor": "transparent", "color": "transparent"},
                tooltip=folium.features.GeoJsonTooltip(fields=["name"], aliases=["지역:"]),
            ).add_to(m)

        map_data = st_folium(m, width=600, height=500, key=f"map_{viz_mode}")
        if map_data and map_data.get("last_active_drawing"):
            clicked = map_data["last_active_drawing"]["properties"]["name"]
            for _, rrow in df_stats.iterrows():
                if rrow["region_full"].startswith(clicked[:2]) or clicked.startswith(rrow["region"][:2]):
                    st.session_state.selected_region = rrow["region"]
                    break

        if col is None:
            with st.expander("🎨 16색 페르소나 범례"):
                legend_cols = st.columns(4)
                for i, (p, c) in enumerate(PERSONA_COLORS.items()):
                    with legend_cols[i % 4]:
                        st.markdown(
                            f"<div style='display:flex;align-items:center;gap:6px;padding:2px 0'>"
                            f"<div style='width:16px;height:16px;background:{c};"
                            f"border:1px solid #555;border-radius:3px'></div>"
                            f"<span style='font-family:monospace;font-size:13px'>{p}</span>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )

    with col_info:
        st.subheader("🔍 지역 분석")
        st.text_input(
            "거주하시거나 궁금한 지역을 입력하세요 (예: 서울, 부산, 강원도)",
            key="region_input",
            on_change=on_region_input,
        )

        selected = st.session_state.selected_region
        if selected not in df_stats["region"].values:
            selected = df_stats["region"].iloc[0]
            st.session_state.selected_region = selected
        region_data = df_stats[df_stats["region"] == selected].iloc[0]
        persona = region_data["persona_code"]
        full_name = region_data["region_full"]
        p_color = PERSONA_COLORS.get(persona, "#888")

        nickname, summary = PERSONA_NICKNAMES.get(persona, ("", ""))
        st.markdown(
            f"<div style='padding:14px;background:{p_color}33;"
            f"border-left:6px solid {p_color};border-radius:6px;margin-bottom:10px'>"
            f"<div style='font-size:14px;color:#666'>🎯 {full_name}의 Car-BTI</div>"
            f"<div style='font-size:28px;font-weight:bold;letter-spacing:4px'>[ {persona} ]</div>"
            f"<div style='font-size:16px;font-weight:600;color:#333;margin-top:8px'>{nickname}</div>"
            f"<div style='font-size:13px;color:#555;line-height:1.5;margin-top:4px'>{summary}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        st.plotly_chart(make_radar(full_name, region_data), use_container_width=True)

        with st.expander("📖 페르소나 4축 상세 설명", expanded=True):
            st.markdown(persona_desc_html(persona), unsafe_allow_html=True)

        with st.expander("📊 차량 통계 요약"):
            st.progress(min(int(region_data["eco_ratio"] * 4), 100),
                        text=f"⚡ 친환경 차량 비율: {region_data['eco_ratio']:.2f}%")
            st.progress(min(int(region_data["large_ratio"] * 5), 100),
                        text=f"🚙 대형 승용차 비율: {region_data['large_ratio']:.2f}%")
            st.progress(min(int(region_data["female_ratio"] * 2.5), 100),
                        text=f"👩 여성 등록 비율: {region_data['female_ratio']:.2f}%")
            st.progress(min(int(region_data["import_ratio"] * 4), 100),
                        text=f"🌍 수입차 비율: {region_data['import_ratio']:.2f}%")

    st.divider()

    st.subheader(f"🚗 [{persona}] 페르소나 매칭 차량")
    render_recommended_cars(persona, cars_df)

    st.divider()

    render_news_section(persona, cars_df, title=f"📰 [{persona}] 추천 차량 관련 최신 뉴스")

    st.divider()

    st.subheader(f"💬 [{persona}] 성향 맞춤 FAQ")
    render_faq_list(persona, faq_df, cars_df, top_n=10)


# ════════════════════════════════════════
# Tab 2: 나의 Car-BTI 테스트
# ════════════════════════════════════════
with tab2:
    st.subheader("🧪 나의 Car-BTI 테스트")
    st.caption("4가지 질문에 답하시면 본인의 Car-BTI와 가장 비슷한 지역, 1:1 매칭 차량, 맞춤 FAQ를 보여드립니다.")

    q1 = st.radio(
        "**Q1.** 다음 차량 중 더 끌리시는 쪽은?",
        ["⚡ 전기차/하이브리드 등 친환경", "⛽ 내연기관(가솔린/디젤/LPG)"],
        key="t_q1",
    )
    q2 = st.radio(
        "**Q2.** 주말에 차량을 주로 어떻게 활용하시나요?",
        ["🏕️ 캠핑·패밀리·레저 — SUV/대형이 필요", "🏙️ 도심 주행·주차 편의 — 소형/세단을 선호"],
        key="t_q2",
    )
    q3 = st.radio(
        "**Q3.** 운전자 성별은?",
        ["👨 남성", "👩 여성"],
        key="t_q3",
    )
    q4 = st.radio(
        "**Q4.** 브랜드 선호도는?",
        ["🌍 수입 브랜드 (벤츠/BMW/볼보 등)", "🇰🇷 국산 브랜드 (현대/기아/제네시스 등)"],
        key="t_q4",
    )

    if st.button("🚀 내 Car-BTI 확인하기", type="primary", use_container_width=True):
        my_persona = (
            ("E" if q1.startswith("⚡") else "G")
            + ("L" if q2.startswith("🏕") else "S")
            + ("F" if q3.startswith("👩") else "M")
            + ("I" if q4.startswith("🌍") else "D")
        )
        my_color = PERSONA_COLORS.get(my_persona, "#888")

        st.divider()

        my_nickname, my_summary = PERSONA_NICKNAMES.get(my_persona, ("", ""))
        st.markdown(
            f"<div style='padding:24px;background:{my_color}33;"
            f"border-left:8px solid {my_color};border-radius:8px;margin-bottom:14px'>"
            f"<div style='font-size:16px;color:#666'>🎯 당신의 Car-BTI는</div>"
            f"<div style='font-size:40px;font-weight:bold;letter-spacing:6px'>[ {my_persona} ]</div>"
            f"<div style='font-size:20px;font-weight:600;color:#222;margin-top:10px'>{my_nickname}</div>"
            f"<div style='font-size:14px;color:#444;line-height:1.6;margin-top:6px'>{my_summary}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        st.markdown("##### 📖 당신의 4축 분석")
        st.markdown(persona_desc_html(my_persona), unsafe_allow_html=True)

        st.divider()

        st.markdown("##### 🗺️ 당신과 가장 비슷한 지역 Top 3")
        stats = df_stats.copy()
        stats["_score"] = stats["persona_code"].apply(
            lambda p: sum(1 for a, b in zip(p, my_persona) if a == b)
        )
        top3 = stats.sort_values("_score", ascending=False).head(3)

        cols = st.columns(3)
        rank_emojis = ["🥇", "🥈", "🥉"]
        for i, (_, row) in enumerate(top3.iterrows()):
            with cols[i]:
                rcolor = PERSONA_COLORS.get(row["persona_code"], "#888")
                st.markdown(
                    f"<div style='padding:14px;background:{rcolor}22;"
                    f"border-left:4px solid {rcolor};border-radius:6px;text-align:center'>"
                    f"<div style='font-size:32px'>{rank_emojis[i]}</div>"
                    f"<div style='font-size:18px;font-weight:bold;margin:6px 0'>{row['region_full']}</div>"
                    f"<div style='font-family:monospace;font-size:20px;letter-spacing:3px'>{row['persona_code']}</div>"
                    f"<div style='font-size:13px;color:#666;margin-top:6px'>4자리 중 {row['_score']}자리 일치</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        st.divider()

        st.markdown(f"##### 🚗 당신([{my_persona}])을 위한 추천 매칭 차량")
        render_recommended_cars(my_persona, cars_df)

        st.divider()

        render_news_section(my_persona, cars_df, title=f"📰 당신([{my_persona}])의 추천 차량 관련 최신 뉴스")

        st.divider()

        st.markdown("##### 💬 성향 맞춤 큐레이션 FAQ")
        render_faq_list(my_persona, faq_df, cars_df, top_n=10)


# ════════════════════════════════════════
# Tab 3: AI 상담 챗봇
# ════════════════════════════════════════
with tab3:
    st.subheader("💬 Car-BTI AI 상담")
    st.caption(
        "FAQ·차량 추천·지역 분석·자동차 뉴스·Car-BTI 진단을 AI에게 물어보세요. "
        "답변은 DB와 뉴스 API 데이터를 근거로 생성됩니다."
    )
    chat_ctx = ChatContext(
        faq_df=faq_df,
        cars_df=cars_df,
        region_df=df_stats,
        persona_meta=PERSONA_NICKNAMES,
        recommend_fn=get_recommended_cars,
        news_fn=_chatbot_news_fn,
        region_full_map=REGION_FULL_MAP,
    )
    render_chatbot(chat_ctx)