# OO과정 n차 프로젝트

## 1. 팀 소개

- 팀명 :
- 멤버 개인 깃허브 계정과 연동 : 각자 넣을 것
- 팀역할
    - 노민환 : 국토부 엑셀 데이터 전처리·ERD 설계·Streamlit UI/DB 연동·공통 변수/함수명 조율
    - 이홍규 : MySQL DB 아키텍처 설계·테이블 생성·CSV 적재 파이프라인 구축
    - 김대호 : 브랜드/K Car FAQ 크롤링·차량 이미지 수집·크롤링 데이터 정제
    - 전진영 : Car-BTI 결과 이미지·다운로드 기능·기능 QA

---

## 2. 프로젝트 개요

- 프로젝트 명 : Car-BTI
- 프로젝트 소개 :  
  전국 17개 시·도 자동차 등록 데이터를 기반으로 친환경성/차 규모/성별/제조국 4축을 MBTI 스타일 16유형(Car-BTI)으로 분석하고, 지역별 통계·페르소나 매칭 차량·브랜드 FAQ·뉴스를 제공하는 Streamlit 기반 웹 대시보드
- 프로젝트 필요성(배경) :  
  지역별 자동차 소비 성향을 직관적으로 비교할 수 있는 분석 도구가 필요하며, 공공 통계 데이터를 사용자 친화적인 형태로 제공해 차량 구매 전 탐색·비교·의사결정을 돕기 위함
- 프로젝트 목표 :  
  전국 자동차 등록 데이터를 Car-BTI 지표로 구조화하고, 사용자 성향에 맞는 지역 인사이트·차량 추천·브랜드 FAQ를 통합 제공함으로써 차량 구매 전 의사결정을 돕는 데이터 기반 개인화 서비스(MVP)를 구현한다. 단순 통계 조회를 넘어 실사용 가능한 상담형 자동차 정보 상품으로 확장 가능한 기반을 마련하는 것을 목표로 함

---

## 3. 기술 스택

| 구분 | 기술 |
|------|------|
| **Frontend / UI** | Streamlit, Folium, streamlit-folium, Plotly |
| **Backend** | Python, Pandas |
| **Database** | MySQL, PyMySQL, SQLAlchemy |
| **Crawling / Data** | BeautifulSoup4, Selenium, webdriver-manager, requests, openpyxl |
| **외부 API** | 네이버 뉴스 검색 API, GeoJSON(전국 시도 경계) |
| **AI** |  |

---

## 4. WBS

- 첨부 파일 : `docs/WBS.csv`

| 구분 | 작업 | 기능상세 | 완료여부 |
|------|------|----------|----------|
| 기획 및 설계 | 주제 선정 | Car-BTI(자동차 소비성향 4축 16유형) 컨셉 확정 | 완료 |
| 기획 및 설계 | 데이터 탐색 | 국토부 자동차 등록자료 통계(6개월) 확보·분석 | 완료 |
| 기획 및 설계 | ERD 작성 | region_stats·persona_cars·company_faq 등 설계 | 완료 |
| 기획 및 설계 | WBS 작성 | 작업 분해 및 일정 정의 | 완료 |
| 기획 및 설계 | Git 브랜치 전략 정의 | 브랜치/커밋 규칙 수립 | 완료 |
| 기획 및 설계 | 디자인 컨셉 정의 | 16색 페르소나·대시보드 UI 컨셉 | 완료 |
| 기획 및 설계 | 프로젝트 디렉터리 구조 설정 | crawler·data·docs 등 구조화 | 완료 |
| 기획 및 설계 | 프로젝트 생성 | 저장소·가상환경·의존성 초기화 | 완료 |
| 개발-DB구축 | MySQL DB 생성 | car_bti 데이터베이스 생성 | 완료 |
| 개발-DB구축 | TABLE 생성 | region_stats·persona_cars·company_faq 등 생성 | 완료 |
| 개발-DB구축 | 크롤링 데이터 연동 | FAQ·차량 이미지 등 DB 적재 | 완료 |
| 개발-DB구축 | API 데이터 연동 | 뉴스·지도 데이터 연동 | 완료 |
| 개발-데이터 처리 | XLSX→CSV 변환 | region_ETL.py 기반 시트 전처리 및 DB 설계 | 완료 |
| 개발-데이터 처리 | 페르소나 코드 산출 | 랭크 기준 4자리 코드 부여 | 완료 |
| 개발-데이터 처리 | CSV→MySQL 적재 | 전처리 CSV DB 적재 | 완료 |
| 개발-웹 크롤링 | 브랜드 공식 FAQ 크롤링 | 제네시스·현대·기아·BMW·미니 등 | 완료 |
| 개발-웹 크롤링 | K Car 옥션 FAQ 크롤링 | Selenium 6개 탭 수집 | 완료 |
| 개발-웹 크롤링 | 차량 이미지 크롤링 | 위키피디아 인포박스 이미지 수집 | 완료 |
| 개발-웹 크롤링 | Fallback 시드 구성 | 크롤링 불가 브랜드 대표 FAQ | 완료 |
| 개발-API 콜 및 변환 | 네이버 뉴스 API KEY 발급 | Client ID/Secret 발급·환경변수 관리 | 완료 |
| 개발-API 콜 및 변환 | 뉴스 API 호출 및 정제 | news_api.py 최신 뉴스 조회 | 완료 |
| 개발-API 콜 및 변환 | 지도 API 콜 | GeoJSON 시도 경계 데이터 로드 | 완료 |
| 개발-STREAMLIT 구현 | Main Page/헤더 구현 | 타이틀·축 설명·탭 구성 | 완료 |
| 개발-STREAMLIT 구현 | 지역 분석 Page 구현 | 지도 5모드·레이더 차트 | 완료 |
| 개발-STREAMLIT 구현 | 페르소나 매칭 차량 구현 | 1:1 추천 차량 카드 | 완료 |
| 개발-STREAMLIT 구현 | 성향 맞춤 FAQ 구현 | 브랜드별 라운드로빈 FAQ | 완료 |
| 개발-STREAMLIT 구현 | 추천 차량 뉴스 섹션 구현 | 네이버 뉴스 연동 표시 | 완료 |
| 개발-STREAMLIT 구현 | 나의 Car-BTI 테스트 Page 구현 | 4문항 진단→결과 분석 | 완료 |
| 개발-STREAMLIT 구현 | 페르소나 이미지 카드·다운로드 | 다운로드 기능 구현 | 완료 |
| 개발-STREAMLIT 구현 | 지역 검색 기능 | 지역 검색 값에 맞는 Car-BTI 표현 | 완료 |
| 개발-STREAMLIT 구현 | 통계 그래프 | 선택 기준에 따른 통계값 표현 | 완료 |
| 개발-STREAMLIT 구현 | 차량 통계 요약 | 선택 지역의 비율 요약 | 완료 |
| 테스트 및 마무리 | DB 적재 점검 | check_db.py 상태 점검 | 완료 |
| 테스트 및 마무리 | README/문서화 | 실행법·구조·설정 가이드 | 완료 |

---

## 5. 요구사항 명세서

- 기준 문서 : `docs/요구사항정의서.csv` (회의록 기반 보완 예정)
- 사진 첨부 예정

| 요구사항 ID | 요구사항명 | 기능 요구사항 | 상태 |
|-------------|-----------|--------------|------|
| REQ_001 | MySQL DB 생성 | `car_bti` 데이터베이스 스키마 설계 및 생성 | 완료 |
| REQ_002 | TABLE 생성 | `region_stats`·`persona_cars`·`company_faq` 등 테이블 생성 | 완료 |
| REQ_003 | 국토부 데이터 전처리 | XLSX→CSV 변환 및 4축 비율·페르소나 코드 산출 | 완료 |
| REQ_004 | region_stats 적재 | 처리된 CSV를 MySQL `region_stats`에 적재 | 완료 |
| REQ_005 | 브랜드 FAQ 크롤링 | 10개 브랜드 공식 FAQ 수집·적재(실패 시 시드) | 완료 |
| REQ_006 | K Car 옥션 FAQ 크롤링 | Selenium 기반 6개 탭 FAQ 수집 | 완료 |
| REQ_007 | 차량 이미지 크롤링 | 위키피디아 이미지 수집·LONGBLOB 저장 | 완료 |
| REQ_008 | 네이버 뉴스 API 연동 | 추천 차량/브랜드 기반 최신 뉴스 조회 | 완료 |
| REQ_009 | 지도 시각화 데이터 연동 | GeoJSON 기반 17개 시도 지도 렌더링 | 완료 |
| REQ_010 | Main/지역 분석 Page | 지도 5모드·레이더·페르소나 분석 UI | 완료 |
| REQ_011 | Car-BTI 테스트 Page | 4문항 진단→페르소나 산출·유사 지역/차량 | 완료 |
| REQ_012 | 맞춤 FAQ/추천 차량 Page | 페르소나 기반 FAQ·차량 카드 노출 | 완료 |

---

## 6. ERD

- DB명 : `car_bti`
- 데이터 기간 : 6개월 (`202512` ~ `202605`)
- `year_month` 형식 : `yyyymm` (char(6))

### 주요 테이블

| 테이블명 | 설명 |
|----------|------|
| `region_stats` | 연월·지역별 4축 비율 및 `persona_code` 집계 결과 |
| `tbl_fuel` | 연료별 등록 통계 |
| `tbl_size` | 차량 크기별 등록 통계 |
| `tbl_genderage` | 성별·연령별 등록 통계 |
| `tbl_import` | 시군구별 수입차 등록 통계 |
| `tbl_total` | 시군구별 전체 등록 통계 |
| `tbl_persona_detail` | 16가지 Car-BTI 코드·특징·키워드·설명 |
| `persona_cars` | 페르소나별 추천 차량(64대) 및 이미지 |
| `company_faq` | 브랜드/K Car FAQ |

### Car-BTI 산출 기준 (랭크 8:9 분할)

| 축 | 1~8위 | 9~17위 |
|----|-------|--------|
| 연료 | E (친환경) | G (내연) |
| 차량 크기 | L (대형) | S (소형) |
| 성별 | F (여성) | M (남성) |
| 수입 여부 | I (수입) | D (국산) |

### 데이터 흐름

```
월별 원본 Excel
    ↓
Python 전처리 (region_ETL.py)
    ↓
year_month 컬럼 추가 CSV 생성
    ↓
원본 테이블 적재
(tbl_fuel / tbl_size / tbl_genderage / tbl_import / tbl_total)
    ↓
집계·분석 (view_region_persona)
    ↓
region_stats 저장
    ↓
persona_code 기준 tbl_persona_detail, persona_cars 연결
```

- ERD 이미지 : (첨부 예정)

---

## 7. 주요 프로시저

| 프로시저명 | 기능 | 주요 파라미터 |
|-----------|------|--------------|
| `sp_get_region_persona` | 지역 Car-BTI 조회 | region, year_month |
| `sp_get_same_persona_regions` | 동일 Car-BTI 지역 조회 | region, year_month |
| `sp_get_regions_by_persona` | 페르소나별 지역 조회 | persona_code, year_month |
| `sp_get_top_regions_by_metric` | 지표 상위 지역 조회 | metric, year_month, limit |
| `sp_get_erd_distribution` | ERD 집계 분포 조회 | table, dim_col, region, year_month, limit |
| `sp_get_erd_top_regions` | ERD 집계 상위 지역 | table, dim_col, dim_value, year_month, limit |
| `sp_get_persona_detail` | 페르소나 상세 조회 | persona_code |
| `sp_get_recommended_cars` | 페르소나 추천 차량 조회 | persona_code |
| `sp_search_company_faq` | 브랜드 FAQ 검색 | company, keyword, limit |

- View : `view_region_persona`
- SQL 스크립트 : (첨부 예정)

### 실행 예시

```sql
CALL sp_get_region_persona('서울', '202605');
CALL sp_get_same_persona_regions('부산', '202605');
CALL sp_get_regions_by_persona('ESFI', '202605');
CALL sp_get_top_regions_by_metric('eco_ratio', '202605', 5);
CALL sp_search_company_faq('기아', '전기차', 3);
```

---

## 8. 수행결과(테스트 및 시연 페이지, 캡처본)

### 실행 방법

```bash
# 1. 가상환경 및 패키지
python -m venv myvenv
myvenv\Scripts\activate
pip install -r requirements.txt

# 2. 환경 변수 (.env.example 참고)
# MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
# NAVER_CLIENT_ID, NAVER_CLIENT_SECRET

# 3. DB 초기화 및 데이터 적재
python setup_db.py
python region_ETL.py
python crawler/crawl_brand_faq.py
python crawler/crawl_faq.py
python crawler/crawl_car_images.py
python check_db.py

# 4. 실행
streamlit run app.py
```

- 시연 페이지 : `http://localhost:8501`

### 주요 시연 시나리오

**Tab 1 · 지역 분석**
- 지도 5모드(친환경/대형/여성/수입/16색 페르소나) 전환
- 월 선택(`202512`~`202605`) 및 지역 검색
- 선택 지역 레이더 차트·6개월 추이 그래프
- 페르소나 매칭 차량·맞춤 FAQ·최신 뉴스

**Tab 2 · 나의 Car-BTI 테스트**
- 4문항 설문 → Car-BTI 4자리 코드 산출
- 유사 지역 Top 3·추천 차량·맞춤 FAQ
- 페르소나 이미지 카드 표시 및 다운로드

- 테스트 결과/캡처본 : (한 명이 맡아서 Streamlit 화면 녹화 영상 + 캡처본 첨부 예정)

---

## 9. 한 줄 회고

- 노민환 :
- 이홍규 :
- 김대호 :
- 전진영 :

---

## 10. 추가 고려

### 트러블슈팅

| 이슈 | 원인 | 해결 |
|------|------|------|
| Main App 실행 시 테이블 DROP 오류 | `setup_db.py`의 DROP TABLE이 기존 공유 테이블과 충돌 | DROP 구문 주석 처리 후 정상 동작, `TRUNCATE` 방식 전환 검토 |
| 단일 월 데이터 한계 | 초기 1개월 데이터만 적재 | `year_month` 컬럼 추가 후 6개월치 누적 적재 구조로 변경 |
| 크롤링 실패 브랜드 | 일부 브랜드 사이트 크롤링 불가 | `faq_fallback.py` 시드 FAQ로 대체 |

### 테스트 시나리오 / QA·UI·UX 개선 방향

- [ ] 17개 시도 지도 클릭·지역 검색 시 Car-BTI 정상 반영
- [ ] 월 선택 시 통계·그래프·추천 정보 갱신
- [ ] 4문항 테스트 후 유사 지역 Top3·추천 차량·FAQ 일치 여부
- [ ] 페르소나 이미지 표시 및 다운로드 동작
- [ ] 네이버 뉴스 API 키 미설정 시 안내 메시지 표시
- [ ] 추천 차량 브랜드와 FAQ 브랜드 매칭 일관성 검증

### 기능 흐름도 / 아키텍처 구조도

- 담당 : (한 명 지정 예정)
- 참고 문서 : `docs/아키텍처_기능흐름도.md`

### UI 시안 or UX Flow

- 보류

### 향후 개선 계획

- [ ] 공공데이터 엑셀 자동 다운로드 → CSV 변환 → DB 적재 파이프라인 자동화
- [ ] 하드코딩된 차량 정보를 DB 기반 조회로 전환
- [ ] Car-BTI 설명 데이터를 `tbl_persona_detail`에서 동적 조회
- [ ] 결과 공유용 Car-BTI 이미지 카드 고도화(SNS 공유 고려)
- [ ] Stored Procedure 기반 조회로 애플리케이션 SQL 표준화

### 역할 분담 & 협업 방식

| 담당 | 역할 |
|------|------|
| 노민환 | 데이터 전처리·ERD·Streamlit UI/DB 연동 |
| 이홍규 | DB 설계·구축·적재 |
| 김대호 | 크롤링(FAQ·이미지) |
| 전진영 | Car-BTI 이미지·QA |

- 협업 방식 : **GitHub Flow**
  - `main` : 배포/시연용 안정 브랜치
  - `feature/*` : 기능별 개발 브랜치
  - PR 리뷰 후 merge
  - 공통 변수명·DB 컬럼명·페르소나 코드 규격 사전 공유
