"""
region_ETL.py
================
국토부 자동차 등록 통계 xlsx → Car-BTI 4축 시도별 데이터 추출

산출물
------
  ETL_data/region_stats.csv : 시도별 4축 비율 + persona_code(4글자)
  콘솔                  : 결과 표 + 페르소나 분포

4축 정의 (rank 기준으로 8 : 9 분할)
"""

import os
import pandas as pd

# ──────────────────────────────────────────────
# 경로 / 임계값 / 상수
# ──────────────────────────────────────────────
XLSX_PATH  = "data/2026년_05월_자동차_등록자료_통계.xlsx"
OUTPUT_CSV = "ETL_data/region_stats.csv"

REGIONS = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
           "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]


# 친환경 연료 분류
GREEN_FUELS = [
    "전기", "수소", "수소전기",
    "하이브리드(휘발유+전기)", "하이브리드(경유+전기)",
    "하이브리드(LPG+전기)",   "하이브리드(CNG+전기)",
    "하이브리드(LNG+전기)",
]


# ──────────────────────────────────────────────
# 시트별 추출 함수
# ──────────────────────────────────────────────
def extract_eco(xlsx: str):
    """시트 10 [연료별_등록현황] → (친환경 등록수, 전체 등록수) per 시도"""
    df = pd.read_excel(xlsx, sheet_name="10.연료별_등록현황", header=None)
    df[0] = df[0].ffill()

    sub = df[(df[1] == "소계") & (df[2] == "계")].copy()
    sub.columns = ["연료", "종별", "용도"] + REGIONS + ["총계"]
 
    green = sub[sub["연료"].isin(GREEN_FUELS)][REGIONS].sum()
    
    exclude_items = ["총계", "피견인차", "기타연료", "미상"]
    total = sub[~sub["연료"].isin(exclude_items)][REGIONS].sum()
    
    return green.astype(int), total.astype(int)


def extract_large(xlsx: str):
    """시트 17 [차종별_규모별] → (대형 승용차, 전체 승용차) per 시도"""
    df = pd.read_excel(xlsx, sheet_name="17.차종별_규모별 등록현황_초소형", header=None)
    df[0] = df[0].ffill()
    df.columns = ["시도", "규모", "승용", "승합", "화물", "특수", "계"]
    
    df = df[df["시도"].isin(REGIONS) & df["규모"].notna()].copy()
    df = df[~df["규모"].isin(["계", "합계", "총계"])]
    
    df["승용"] = pd.to_numeric(df["승용"], errors="coerce")
    large = df[df["규모"] == "대형"].groupby("시도")["승용"].sum()
    total = df.groupby("시도")["승용"].sum()
    return (large.reindex(REGIONS).astype(int),
            total.reindex(REGIONS).astype(int))


def extract_gender(xlsx: str):
    """시트 04 [성별_연령별] → (여성 등록수, 남성 등록수) per 시도. 기타(법인) 제외"""
    df = pd.read_excel(xlsx, sheet_name="04.성별_연령별", header=None)
    df[0] = df[0].ffill()
    df.columns = ["성별", "연령", "총계"] + REGIONS
    male   = df[(df["성별"] == "남성") & (df["연령"] == "계")][REGIONS].iloc[0]
    female = df[(df["성별"] == "여성") & (df["연령"] == "계")][REGIONS].iloc[0]
    return female.astype(int), male.astype(int)


def extract_import(xlsx: str):
    """시트 02(전체) + 시트 03(수입차) → (수입차 등록수, 전체 등록수) per 시도"""
    df2 = pd.read_excel(xlsx, sheet_name="02.통계표_시군구", header=None)
    df3 = pd.read_excel(xlsx, sheet_name="03.수입차_시군구", header=None)
    df2[0] = df2[0].ffill()
    df3[0] = df3[0].ffill()
    df2 = df2[~df2[1].isin(["계", "소계", "합계"])]
    df3 = df3[~df3[1].isin(["계", "소계", "합계"])]

    total = (df2[df2[0].isin(REGIONS)]
             .groupby(0)[21]
             .apply(lambda s: pd.to_numeric(s, errors="coerce").sum())
             .reindex(REGIONS).astype(int))
    imp = (df3[df3[0].isin(REGIONS)]
           .groupby(0)[6]
           .apply(lambda s: pd.to_numeric(s, errors="coerce").sum())
           .reindex(REGIONS).astype(int))
    return imp, total


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────
def main():
    if not os.path.exists(XLSX_PATH):
        raise FileNotFoundError(
            f"❌ 엑셀 파일이 없습니다: {XLSX_PATH}\n"
            f"   → data/ 폴더에 xlsx를 옮겨주세요."
        )

    print(f"📂 입력: {XLSX_PATH}")
    print("─" * 80)

    green,  total_fuel      = extract_eco(XLSX_PATH)
    large,  total_passenger = extract_large(XLSX_PATH)
    female, male            = extract_gender(XLSX_PATH)
    imp,    total_all       = extract_import(XLSX_PATH)

    df = pd.DataFrame({
        "region":       REGIONS,
        "eco_count":    green.values,
        "eco_total":    total_fuel.values,
        "eco_ratio":    (green / total_fuel * 100).round(2).values,
        "large_count":  large.values,
        "large_total":  total_passenger.values,
        "large_ratio":  (large / total_passenger * 100).round(2).values,
        "female_count": female.values,
        "male_count":   male.values,
        "female_ratio": (female / (female + male) * 100).round(2).values,
        "import_count": imp.values,
        "import_total": total_all.values,
        "import_ratio": (imp / total_all * 100).round(2).values,
    })

    # ──────────────────────────────────────────────
    # Rank 기반 페르소나 코드 생성 (17개 지역 대상)
    # ──────────────────────────────────────────────
    # 내림차순으로 순위를 매겨 1등부터 17등까지 부여
    # method="first"로 값이 같으면 데이터 상 먼저 나온 지역에 앞 순위를 줌
    eco_rank = df["eco_ratio"].rank(ascending=False, method="first")
    large_rank = df["large_ratio"].rank(ascending=False, method="first")
    female_rank = df["female_ratio"].rank(ascending=False, method="first")
    import_rank = df["import_ratio"].rank(ascending=False, method="first")
    

    # 분할 비율(8:9)에 맞춰 순위 커트라인 적용
    df["persona_code"] = (
        eco_rank.apply(lambda r: "E" if r <= 8 else "G")
        + large_rank.apply(lambda r: "L" if r <= 8 else "S")
        + female_rank.apply(lambda r: "F" if r <= 8 else "M")  
        + import_rank.apply(lambda r: "I" if r <= 8 else "D")
    )

    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    # 결과 출력
    print("\n🎯 추출 결과 (시도별 4축 비율 + 페르소나 코드)")
    show = df[["region", "eco_ratio", "large_ratio",
               "female_ratio", "import_ratio", "persona_code"]]
    print(show.to_string(index=False))

    print(f"\n💾 저장: {OUTPUT_CSV}  ({len(df)}건)")

    print("\n📊 페르소나 코드별 시도 수:")
    print(df["persona_code"].value_counts().to_string())


if __name__ == "__main__":
    main()