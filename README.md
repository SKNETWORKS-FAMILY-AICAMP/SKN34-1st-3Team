# 🚗 Car-BTI: 전국 자동차 소비 성향 분석 대시보드

**MBTI 스타일 4축 16유형으로 전국 17개 시도의 자동차 등록 현황을 시각화하고, 사용자 맞춤형 차량 추천 및 FAQ를 제공하는 Streamlit 대시보드**

---

## 📌 프로젝트 개요

- **주제**: 전국 자동차 등록 현황 및 기업 FAQ 조회 시스템
- **기술 스택**: Python, Streamlit, MySQL, Pandas, Folium, Plotly, BeautifulSoup, Selenium, Requests, Naver Search API
- **팀 구성**: SKN34기 3팀 (김대호, 노민환, 이홍규, 전진영)
- **데이터 출처**: 국토교통부 2026년 5월 자동차 등록자료 통계
- **크롤링 대상**: 10개 브랜드 공식 FAQ + K Car 옥션 + 시드 데이터 (총 750+건)
- **차량 데이터**: 16개 페르소나별 4대씩 큐레이션 (총 64대) + 위키피디아 이미지
- **뉴스 데이터**: 네이버 뉴스 검색 API를 활용한 추천 차량/브랜드 관련 최신 자동차 뉴스

---

## 🎯 핵심 기능

### 1. 🗺️ 지역별 Car-BTI 분석
- **4축 시각화**: 친환경(E/G) · 대형(L/S) · 성별(F/M) · 수입(I/D)
- **5가지 지도 모드**:
  - 친환경 차량 비율 
  - 대형 승용차 비율 
  - 여성 등록 비율 
  - 수입차 비중
  - 16색 페르소나 매핑
- **레이더 차트**: 선택 지역의 4축 점수 시각화
- **페르소나 매칭**: 지역별 1:1 큐레이션 차량 4대 추천
- **맞춤 FAQ**: 추천 브랜드별 자동 태깅 FAQ 10개

### 2. 🧪 나의 Car-BTI 테스트
- **4문항 진단**: 친환경 여부, 차종(대/소), 성별, 수입/국산 선택
- **결과 분석**: 
  - 본인 페르소나 코드 + 한 줄 요약
  - 4축 상세 설명
  - 비슷한 지역 Top 3 (일치 자리수 표시)
  - 맞춤형 차량 + FAQ

 ### 3. 📰 추천 차량 기반 최신 자동차 뉴스
- **네이버 뉴스 검색 API 연동**: 추천 차량 또는 브랜드명을 기반으로 최신 자동차 뉴스 조회
- **실시간 정보 제공**: 차량 구매·선택에 참고할 수 있는 최신 시장/브랜드/모델 뉴스 제공
- **페르소나별 검색어 자동 생성**: 추천 차량 브랜드와 모델명을 조합해 뉴스 검색
- **안전한 API 키 관리**: `.env` 환경변수로 Client ID / Secret 관리
- **캐싱 적용**: Streamlit 캐시를 사용해 불필요한 API 호출 최소화

---

## 📦 실행

### 1단계: 저장소 클론
```bash
git clone https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-1st-3Team.git
cd SKN34-1st-3Team
```

### 2단계: 가상환경 생성 및 활성화
```bash
# Windows
python -m venv myvenv
myvenv\Scripts\activate

# Mac/Linux
python3 -m venv myvenv
source myvenv/bin/activate
```

### 3단계: 패키지 설치
```bash
pip install -r requirements.txt
```

### 4단계: 환경 변수 설정
```bash
# .env 파일 생성 (템플릿: .env.example)
cp .env.example .env

# .env 내용 수정:
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=car_bti

# 네이버 뉴스 검색 API
NAVER_CLIENT_ID=your_naver_client_id
NAVER_CLIENT_SECRET=your_naver_client_secret
```

### 5단계: 데이터 처리 및 DB 적재

```bash
# Step 1: Excel → CSV 변환 (국토부 데이터)
python prepare_data.py
# → data/region_stats.csv 생성

# Step 2: DB 생성 + persona_cars, company_faq 테이블 생성 + 시드 삽입
python setup_db.py

# Step 3: CSV → MySQL region_stats 테이블 적재
python load_to_mysql.py

# Step 4: 브랜드 공식 FAQ 크롤링
python crawler/crawl_brand_faq.py
# (시간 소요: 5~10분, Selenium 기반)

# Step 5: K Car 옥션 FAQ 크롤링
python crawler/crawl_faq.py

# Step 6: 차량 이미지 크롤링 
python crawler/crawl_car_images.py

# Step 7: DB 적재 상태 점검
python check_db.py
```

### 6단계: Streamlit 실행
```bash
streamlit run app.py
```

브라우저가 자동으로 열리고, 기본 주소는 `http://localhost:8501`

---

## 📂 프로젝트 구조

```
SKN34-1st-3Team/
├── app.py                          # Streamlit 대시보드 (2 탭)
├── prepare_data.py                 # XLSX → CSV (4축 비율 계산)
├── load_to_mysql.py                # CSV → MySQL region_stats 적재
├── setup_db.py                     # persona_cars, company_faq 테이블 생성 + 시드
├── db_config.py                    # MySQL 연결 헬퍼
├── news_api.py                     # 네이버 뉴스 검색 API 호출 및 뉴스 데이터 정제
├── check_db.py                     # DB 적재 상태 점검
├── requirements.txt                # 패키지 목록
├── .env.example                    # 환경 변수 템플릿
├── .gitignore                      # Git 제외 파일
├── README.md                       # (이 파일)
├── data/
│   ├── 2026년_05월_자동차_등록자료_통계.xlsx  # 원본 국토부 데이터
│   └── region_stats.csv            # 처리된 지역 통계 (17행)
├── crawler/
│   ├── crawl_brand_faq.py          # 7개 브랜드 공식 FAQ
│   ├── crawl_car_images.py         # 위키피디아 차량 이미지
│   ├── crawl_faq.py                # K Car 옥션 FAQ (Selenium)
│   ├── faq_common.py               # 공통 유틸 (auto_tag, categorize)
│   └── faq_fallback.py             # 크롤링 불가 브랜드 시드 (15건)
└── db/
    └── images/                     # 로컬 이미지 백업 (gitignore)
```

---

## 🗄️ 데이터베이스 구조 (ERD)

### region_stats (17행)
국토부 Excel에서 추출한 **시도별 4축 비율** 데이터.

| PK | 친환경 | 대형 | 여성 | 수입 | 페르소나 |
|---|---|---|---|---|---|
| region | eco_count, eco_ratio | large_count, large_ratio | female_count, female_ratio | import_count, import_ratio | persona_code |

**임계값 (비율 기준)**:
- 친환경 ≥ 14.0% → E, < 14.0% → G
- 대형 ≥ 14.8% → L, < 14.8% → S
- 여성 ≥ 27.5% → F, < 27.5% → M
- 수입 ≥ 12.0% → I, < 12.0% → D

**예시**:
```
서울: eco_ratio=14.64 (E), large_ratio=17.21 (L), female_ratio=26.73 (M), import_ratio=22.99 (I)
→ persona_code = "ELMI"
```

---


## 📊 화면 구성

### Tab 1: 🗺️ 지역 분석

**A. 지도 시각화**
- 5가지 모드 토글 (친환경, 대형, 여성, 수입, 16색 페르소나)
- Folium 기반 인터랙티브 지도

**B. 지역 분석 패널 (오른쪽)**
- 페르소나 코드 박스 (고유 색상)
- 페르소나 한 줄 요약
- 4축 레이더 차트
- 페르소나 4축 상세 설명
- 차량 통계 progress bar 4개

**C. 페르소나 범례**
- 16색 시각화 (ESMD부터 GLFI까지)

**D. 페르소나 매칭 차량**
- 4대 카드 (이미지 + 브랜드 + 가격 + 추천 사유)

**E. 추천 차량 관련 최신 뉴스**
- 추천 차량 브랜드/모델 기반 네이버 뉴스 API 검색
- 최신순 뉴스 제목, 요약, 발행 시각, 원문 링크 제공

**F. 성향 맞춤 FAQ**
- Top 10 (브랜드별 라운드로빈 + 점수 표시)

### Tab 2: 🧪 나의 Car-BTI 테스트

**A. 4문항 진단**
- Q1: 친환경 vs 내연
- Q2: 대형 vs 소형
- Q3: 남성 vs 여성
- Q4: 수입 vs 국산

**B. 결과 화면**
- 본인 페르소나 박스 (한 줄 요약)
- 4축 분석
- 가장 비슷한 지역 Top 3 (일치 자리수)
- 맞춤형 차량 4대
- 추천 차량/브랜드 관련 최신 자동차 뉴스
- 맞춤형 FAQ Top 10

---

## 🌐 데이터 출처 및 크롤링

### 지역 통계 (region_stats)
- **원본**: 국토교통부 2026년 5월 자동차 등록자료 통계
- **처리**: `prepare_data.py` (xlsx → csv) + `load_to_mysql.py`
- **데이터**: 17개 시도, 14개 컬럼 (eco/large/female/import 각 count/total/ratio)

### 브랜드 공식 FAQ (company_faq)
- **제네시스**: 공식 FAQ 페이지 HTML 크롤링
- **현대**: 고객센터 REST API
- **기아**: FAQ 검색 API
- **BMW/미니**: Salesforce 포털 (Selenium)
- **벤츠/테슬라/볼보/아우디/쉐보레**: 공식 사이트 크롤링 실패 → `faq_fallback.py` 시드 15건
- **K Car 옥션**: Selenium 기반 6개 탭 크롤링

**총 적재 건수**: 약 750+건

### 차량 이미지 (persona_cars)
- **출처**: 영문 위키피디아 차량 인포박스
- **저장 방식**: MySQL LONGBLOB + 로컬 백업 (`db/images/`)
- **크롤링 결과**: 64개 모두 성공

### 자동차 뉴스 API
- **출처**: 네이버 뉴스 검색 API
- **방식**: 추천 차량 브랜드/모델명을 검색어로 조합해 최신 뉴스 조회
- **정렬**: `sort=date` 옵션으로 최신순 조회
- **저장 방식**: DB 저장 없이 Streamlit 실행 중 실시간 조회
- **환경 변수**: `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`

---


## 📚 참고 자료

- [Streamlit 공식 문서](https://docs.streamlit.io/)
- [Folium 지도 시각화](https://folium.readthedocs.io/)
- [BeautifulSoup 웹 크롤링](https://www.crummy.com/software/BeautifulSoup/)
- [Selenium 자동화](https://selenium-python.readthedocs.io/)
- [MySQL Python Connector](https://dev.mysql.com/doc/connector-python/en/)
- [네이버 뉴스 검색 API](https://developers.naver.com/docs/serviceapi/search/news/news.md)
- [네이버 오픈API 목록](https://developers.naver.com/docs/common/openapiguide/apilist.md)

---

**Last Updated**: 2026-06-29 16:40  
