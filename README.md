# 🚗 Car-BTI: 전국 지역별 자동차 소비 성향 분석 대시보드

MBTI처럼 4가지 축의 조합으로 전국 17개 시도의 자동차 소비 성향을 분석

- **E/G** : 친환경(전기차) vs 내연기관
- **L/S** : 대형/SUV vs 소형/세단  
- **F/M** : 여성 강세 vs 남성 강세
- **I/D** : 수입차 vs 국산차

예) 서울 = **ELMI** (친환경 + 대형 + 남성 강세 + 수입차)


## 🚀 빠른 시작 (Windows 기준)

### 1단계: 저장소 클론

```bash
git clone https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-1st-3Team.git
cd carbti
```

### 2단계: 가상환경 생성 및 활성화

```bash
python -m venv myvenv
myvenv\Scripts\activate
```

성공하면 터미널 앞에 `(myvenv)` 가 표시됨 

### 3단계: 패키지 설치

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4단계: MySQL 데이터베이스 생성 (한 번만)

DBeaver 또는 MySQL CLI에서 실행:

```sql
CREATE DATABASE car_bti CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 5단계: .env 파일 설정

프로젝트 폴더에 `.env` 파일을 만들고 아래 내용 입력:

```
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=본인의_MySQL_비밀번호
MYSQL_DATABASE=car_bti
```

### 6단계: 데이터 처리

```bash
python prepare_data.py
python load_to_mysql.py
```

### 7단계: Streamlit 실행

```bash
streamlit run app.py
```

브라우저에서 `http://localhost:8501` 접속 

---

## 📁 폴더 구조

```
carbti/
├── app.py                    # Streamlit 대시보드
├── prepare_data.py           # xlsx → CSV 변환
├── load_to_mysql.py          # CSV → MySQL 적재
├── requirements.txt          # 패키지 목록
├── .env                      # MySQL 비밀번호 (개인용)
├── .env.example              # .env 템플릿
├── README.md                 # 이 파일
├── data/                     # 데이터 폴더
│   ├── 2026년_05월_자동차_등록자료_통계.xlsx
│   └── region_stats.csv
└── crawler/                  # 크롤러 (미정)
```

---

## 🎯 주요 기능

**[🗺️ 지역 분석]**
- 전국 지도 시각화 (친환경/대형/여성/수입/16색 페르소나)
- 지역별 4축 레이더 차트
- 페르소나 매칭 FAQ 리스트

**[🧪 나의 Car-BTI 테스트]**
- 4가지 질문으로 본인 페르소나 진단
- 가장 비슷한 지역 Top 3
- 추천 차량 및 관련 FAQ


## 👥 팀 역할

- **데이터 전처리**: prepare_data.py (4축 추출)
- **DB 적재**: load_to_mysql.py (MySQL 저장)
- **크롤링**: crawler/ (FAQ + 이미지)
- **Streamlit**: app.py (대시보드)

---

## Mac / Linux 사용자

가상환경 활성화 커맨드만 다름:

```bash
python3 -m venv myvenv
source myvenv/bin/activate
```

나머지는 동일
