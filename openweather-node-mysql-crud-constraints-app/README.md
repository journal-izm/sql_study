# OpenWeather + Node.js + MySQL CRUD 학습 프로젝트

기존 `openweather-node-mysql-app`을 **CRUD 학습 단계까지 확장**한 버전입니다.

```text
OpenWeather API
→ Node.js / Express
→ localhost MySQL
→ 기상 데이터 축적
→ GROUP BY / AVG / MAX / MIN
→ 기사 CRUD
```

## CRUD

| 기능 | HTTP | API | SQL |
|---|---|---|---|
| Create | POST | `/api/articles` | INSERT |
| Read | GET | `/api/articles` | SELECT |
| Read 1건 | GET | `/api/articles/:id` | SELECT + WHERE |
| Update | PATCH | `/api/articles/:id` | UPDATE |
| Delete | DELETE | `/api/articles/:id` | DELETE |

## 실행 순서

1. MySQL Workbench에서 `weather_news_crud.sql` 실행
2. `.env.example`을 `.env`로 복사
3. 패키지 설치
4. 서버 실행

```powershell
Copy-Item .env.example .env
npm install
npm start
```

브라우저:

```text
http://localhost:8081
```

## 수업 핵심

```text
POST   → INSERT
GET    → SELECT
PATCH  → UPDATE
DELETE → DELETE
```

다음 단계에서는 `users` 테이블과 로그인/권한 기능을 추가합니다.

## 제약조건 추가 버전
MySQL 8.0.16 이상과 InnoDB를 사용합니다.
- PK: 두 테이블의 자동 증가 ID로 행 구분
- FK: news_article.weather_id → weather_observation.weather_id (1:N)
- UNIQUE: (city_code, observed_at). 같은 도시라도 관측 시각이 다르면 저장 가능
- CHECK: 습도 0~100, 풍속 0 이상, 빈 기사 제목 금지
- CASCADE: 관측값 삭제 시 연결된 기사도 삭제. 기사 삭제는 관측값에 영향 없음
- weatherId 생략 또는 null: 관측값 연결 없는 기사 작성
- PATCH에서 weatherId:null: 기존 연결 해제

처음 만드는 DB: weather_news_crud.sql 실행. 기존 원본 DB: migration_constraints.sql의 사전 조회로 문제를 해결한 뒤 ALTER 실행. CREATE TABLE IF NOT EXISTS는 기존 구조를 바꾸지 않습니다. 두 앱은 동일한 스키마를 사용하므로 같은 DB에는 마이그레이션을 한 번만 실행합니다.

수집 결과 로그의 weather_id를 기사 생성 입력칸에 넣으세요. API 예: POST /api/articles 에 {"weatherId":1,"title":"서울 기상 기사"}. 같은 관측값 재수집은 409, 없는 weatherId는 409, CHECK 위반은 400을 반환합니다.

학습용 CASCADE 삭제 예: DELETE FROM weather_observation WHERE weather_id=1; 연결된 기사도 삭제됩니다. 기사 근거 보존이 필요한 서비스에서는 RESTRICT, 기사만 남기려면 SET NULL을 선택하세요. ON DELETE RESTRICTED는 잘못된 문법입니다.

constraints_test.py로 PK/FK/UNIQUE/CHECK/CASCADE를 실제 DB에서 검증할 수 있습니다. python -m pip install pymysql python-dotenv 후 python constraints_test.py 실행. 테스트 행은 트랜잭션을 롤백합니다.
