# openweather-fastapi-mysql-crud-constraints-app

## 목적

OpenWeather 기상 수집과 기사 CRUD에 MySQL 제약조건을 적용하는 학습 프로젝트입니다.

```text
OpenWeather API
→ FastAPI
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
| Read 1건 | GET | `/api/articles/{id}` | SELECT + WHERE |
| Update | PATCH | `/api/articles/{id}` | UPDATE |
| Delete | DELETE | `/api/articles/{id}` | DELETE |

## 실행 순서

1. MySQL Workbench에서 `weather_news_crud.sql` 실행
2. `.env.example` → `.env` 복사
3. 가상환경 생성/실행
4. 패키지 설치
5. FastAPI 실행

저장소 루트에서 해당 앱 폴더로 이동한 뒤 실행합니다.

```powershell
cd openweather-fastapi-mysql-crud-constraints-app
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app:app --reload
```

브라우저:

```text
http://127.0.0.1:8000
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

## 수업 핵심

```text
POST   → INSERT
GET    → SELECT
PATCH  → UPDATE
DELETE → DELETE
```

다음 단계에서는 `users` 테이블을 추가하고 로그인/권한 기능으로 확장합니다.

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

## 관련 실습

- [저장소 학습 안내](../README.md)
- [Workbench JOIN·제약조건 실습](../sql-weather_constraints_lab/weather_mysql_join_constraints_lab.sql)

SQL 단독 실습 DB는 `weather_constraints_lab`, 이 앱의 기본 DB는 `weatherNewsDB`입니다.



## PUT / PATCH 비교 실습

- PATCH `/api/articles/{id}`: 전송한 항목만 수정. 예: `{"status":"APPROVED"}`. 나머지는 유지.
- PUT `/api/articles/{id}`: 수정 가능한 6개 항목 전체 교체. 생략은 오류. 선택 항목은 null로 명시.
- PUT은 기존 기사만 수정합니다. 없는 ID는 404이며 자동 생성하지 않습니다.
- UI: 기사 ID 입력 → “전체 교체 (PUT) 펼치기” → “기사 불러오기” → 편집 → “전체 교체 (PUT)”.
- 빈 선택 항목은 null로 교체되므로 유지할 내용은 먼저 불러오세요.
- ID, created_at은 유지하며 updated_at은 DB가 관리합니다. SQL 스키마 변경은 없습니다.

PUT 요청 예시 (실제 생성된 기사 ID 사용):
```json
{"sourceRegion":"서울","title":"서울 날씨 뉴스","leadText":null,"bodyText":"수정된 본문","status":"REVIEW","weatherId":null}
```

검증 순서: POST로 기사 생성 → GET 확인 → PATCH 상태만 수정 → GET에서 본문 유지 확인 → PUT 전체 교체 → GET 확인 → 같은 PUT 재요청(성공) → PUT에서 title 누락(입력 오류) → 존재하지 않는 weatherId로 FK 오류 확인.

Node 입력 오류는 400, FastAPI 모델 검증 오류는 422입니다. FK 위반은 409입니다.

### FastAPI /docs에서 테스트

서버 실행 후 http://localhost:8000/docs (실제 uvicorn 포트 사용)를 엽니다.
POST로 기사 생성 후 응답 article_id를 기록합니다.
PATCH 또는 PUT `/api/articles/{article_id}` → Try it out → ID/JSON 입력 → Execute.
PATCH는 바꿀 항목만 남기고, PUT은 위 예시의 6개 필드를 모두 입력합니다.
