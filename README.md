# SKN34-1st-3Team
3팀
김대호
노민환
이홍규
전진영

# 0. 클론
git clone https://github.com/.../carbti.git
cd carbti

# 1. 가상환경 (Windows 기준)
python -m venv myvenv
myvenv\Scripts\activate

# 2. 패키지 설치
pip install -r requirements.txt

# 3. .env 설정 (본인 MySQL 비밀번호 입력)
cp .env.example .env
# 에디터로 열어서 MYSQL_PASSWORD 수정

# 4. MySQL DB 생성 (한 번만)
# DBeaver에서 실행:
# CREATE DATABASE car_bti CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

# 5. 데이터 처리
python prepare_data.py
python load_to_mysql.py

# 6. 앱 실행!
streamlit run app.py