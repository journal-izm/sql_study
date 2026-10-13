# 실제 기상 관측 CSV → MySQL → 근거 → 기사 초안

기존 Python CLI의 `import-csv → compare → save-article` 흐름을 유지합니다. `save-article`은 사람이 쓴 본문을 저장하는 기존 명령입니다. 이번 버전에서 `generate-article`을 추가하여 같은 근거로 **템플릿 / 무료 로컬 Hugging Face / OpenAI API** 중 한 방식을 고를 수 있습니다. 예보 앱이나 웹 프레임워크로 바꾸지 않습니다.

## 1. 먼저 데이터 종류를 구분합니다

| 입력 | 사용할 명령 | 할 수 있는 분석 |
|---|---|---|
| ASOS **일자료**, `평균기온(℃)`, 날짜만 있는 `일시` | `import-csv` → `compare` | 서로 다른 두 해의 같은 달 비교. 두 달 모두 완전해야 함 |
| ASOS **시간자료**, `기온(°C)`, 날짜+시간의 `일시` | `summarize-hourly` | 완전한 날짜의 시간 관측 기온 평균. CSV/JSON 파일만 사용 |

시간자료를 일자료 테이블에 넣거나 `기온`을 `평균기온`으로 이름만 바꾸면 안 됩니다. 코드가 잘못된 입력 종류를 설명하고 중단합니다.

### 제공된 실물 시간 CSV의 적합성

사용자가 제공한 `OBS_ASOS_TIM_20261014010601.csv`를 실제로 검사했습니다. 원본은 Git에 포함하지 않습니다.

- CP949, 38개 열, 1,008행, 서울(108)
- 2026-09-01 01:00~2026-10-13 00:00, 중복 시각/기온 결측 없음
- KST의 **00:00~23:00**을 한 날짜로 삼으면 완전한 날짜는 2026-09-02~2026-10-12, **41일·984시간**입니다.
- 첫날 23시간, 마지막 날 1시간은 평균에서 제외합니다. 원본의 행은 수정하지 않습니다.
- 완전한 날짜의 시간 관측 기온 산술평균: **21.38℃**. 이는 공식 일평균기온·월평균기온이 아닙니다.
- 한 해의 시간자료이므로 기존의 전년 동월 비교에는 부족합니다. 두 해의 **일자료**가 추가로 필요합니다.

ASOS의 시각 표기는 [기상청 APIHub의 시간자료 KST 설명](https://apihub.kma.go.kr/apiList.do)을 따릅니다. CSV 문자열 자체에는 UTC offset이 없어 `Asia/Seoul`로 해석했다는 근거를 JSON에 기록합니다. 다운로드 기간의 01시~다음 날 00시 경계와 여기서 선택한 00~23시 집계 경계를 혼동하지 않습니다.

실물 원본에서 48행·5개 열을 추출한 작은 [테스트 fixture](tests/fixtures/README.md)를 동봉합니다. 추출 방법·원본/발췌 해시·출처를 기록했으며 가상 관측값을 만들지 않았습니다. 포털 재다운로드로 원본의 모든 값을 대조한 것은 아닙니다.

## 2. 일자료 확보와 설치

공식 출처: [기상자료개방포털 ASOS](https://data.kma.go.kr/data/grnd/selectAsosRltmList.do?pgmNo=36)

1. 필요하면 사용자가 포털에 로그인합니다.
2. ASOS, 자료형태 **일**, 지점 **서울**, 요소 **평균기온**을 선택합니다.
3. 완전한 자료가 있는 서로 다른 두 해의 같은 달을 각각 내려받습니다. 아래는 2025년/2026년 9월 예시입니다.
4. `data/raw/seoul_2025_09.csv`, `data/raw/seoul_2026_09.csv`로 보관합니다.
5. 실제 헤더와 지점 코드를 확인합니다. 예시의 `108`은 서울입니다.

| CSV 열 | DB 열 |
|---|---|
| 지점 | station_id |
| 지점명 | station_name |
| 일시 (YYYY-MM-DD) | observed_date |
| 평균기온(℃) | avg_temp_c |

영문 헤더 `station_id,station_name,observed_date,avg_temp_c`, UTF-8 BOM/CP949, 헤더의 공백과 °C/℃ 차이를 지원합니다. 추가 열은 무시하되 행의 열 개수 오류를 거부합니다. 빈 기온은 NULL이며 0℃와 구분합니다. -999, NaN, 소수 2자리 초과 값은 중단합니다. 정제가 필요하면 원본을 보존하고 별도 파일에 작업하세요.

### Windows PowerShell

MySQL 8.0.16 이상(CHECK 적용), Workbench, Python 3.10 이상이 필요합니다. `weather-history-mysql-lab` 폴더에서 실행합니다.

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env`의 `MYSQL_*`를 본인 실습 DB에 맞게 수정합니다. 실제 비밀번호/API 키를 Git에 올리지 않습니다. 새 DB는 Workbench에서 `schema.sql` 전체를 실행합니다. 기존 테이블을 삭제하지 않으며 6개 테이블을 생성합니다.

**기존 버전 사용자:** 기존 DB를 백업한 뒤 `migration_article_generation.sql`을 실행합니다. `CREATE TABLE IF NOT EXISTS`만 다시 실행하면 기존 작성자 CHECK가 바뀌지 않습니다. 마이그레이션은 `TEMPLATE` 작성자를 허용하고 생성 이력 테이블을 추가하며 관측/기사 행을 지우지 않습니다. MySQL DDL은 암묵적 커밋이 발생할 수 있으므로 중간 오류가 나면 결과를 확인한 뒤 재실행하세요.

## 3. 일자료 검증 → DB 저장 → 두 해 비교

```powershell
.venv\Scripts\python.exe weather_lab.py import-csv data/raw/seoul_2025_09.csv --validate-only
.venv\Scripts\python.exe weather_lab.py import-csv data/raw/seoul_2026_09.csv --validate-only
.venv\Scripts\python.exe weather_lab.py import-csv data/raw/seoul_2025_09.csv
.venv\Scripts\python.exe weather_lab.py import-csv data/raw/seoul_2026_09.csv
.venv\Scripts\python.exe weather_lab.py compare --station 108 --baseline-year 2025 --target-year 2026 --month 9
```

- 파일 SHA256이 같으면 재저장을 생략합니다. 다른 파일의 동일 관측소·날짜·기온도 행을 생략합니다.
- 이미 저장된 날짜의 값이 다르면 자동 덮어쓰기하지 않고 파일 전체를 rollback합니다.
- 파일명·SHA256·출처·수집 시각을 보존합니다. 기온 범위 검사는 교육용 입력 검사이며 공식 품질 판정이 아닙니다.
- 비교 근거는 `analysis_result`와 `data/results/fact_sheet.json`에 저장되고 `analysis_id`가 출력됩니다.
- 월 평균 = 일평균기온 합 / 전체 날짜 수. 차이 = 대상 해 평균 − 기준 해 평균. 평균의 차이를 먼저 구한 뒤 소수 둘째 자리로 반올림합니다. 표시 평균끼리의 차이와 0.01℃ 다를 수 있습니다.
- 두 달의 모든 날짜/기온이 있어야 저장합니다. 빠진 날짜, NULL, 미래/진행 중인 달은 중단합니다. 공식 월 통계 산출 절차를 구현한 것은 아닙니다.

`queries.sql`에서 JOIN, 유효 일수, 완전한 달의 평균 차이, 기사 근거를 확인합니다. SQL 조건을 실제 관측소·연도·월에 맞추세요.

## 4. 시간 CSV로 즉시 실습하기 (DB 불필요)

제공받은 원본을 `data/raw/asos_hourly.csv`로 복사하거나 실제 파일 경로를 인수로 전달합니다.

```powershell
.venv\Scripts\python.exe weather_lab.py summarize-hourly data/raw/asos_hourly.csv --station 108 --output data/results/hourly_facts.json
.venv\Scripts\python.exe weather_lab.py generate-article --facts data/results/hourly_facts.json --mode template --output data/results/hourly_template.json
```

완전한 날짜는 정시 24개, 기온 결측 없음, 비어 있지 않은 기온 QC 플래그 없음으로 정의합니다. QC 코드의 의미를 추측하지 않고 플래그가 있는 날짜는 검토 대상으로 제외하는 보수적인 교육용 정책입니다. 날짜 전체가 빠져도 누락으로 기록합니다. 임의 보간하지 않습니다. 원본 CSV와 같은 출력 경로(심볼릭 링크 포함)는 거부하고, 이미 있는 근거 출력은 `--overwrite`를 지정해야 교체합니다. `included_dates`, `excluded_dates`, `coverage`에 선택/제외 이유를 남깁니다. 여러 관측소가 있으면 `--station`을 지정합니다.

`--facts`로 만든 시간자료 기사는 **파일로만 저장**합니다. 기존 일자료 비교 테이블에는 억지로 연결하지 않습니다.

## 5. 같은 근거로 고르는 세 가지 기사 작성 방식

### A. template: 기본값, 무료, API·모델 설치 없음

```powershell
.venv\Scripts\python.exe weather_lab.py generate-article --facts data/results/fact_sheet.json --mode template --output data/results/template_article.json
```

검증된 수치를 정해진 한국어 문장에 넣습니다. 기존의 사람 작성·저장 기능에 새로 추가한 선택지입니다.

### B. huggingface: 공개 모델을 내 컴퓨터에서 무료 추론

기본값은 **[Qwen/Qwen2.5-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct)**입니다. 공식 모델 카드에 한국어 지원이 명시된 1.54B 규모의 Apache-2.0 모델로, 가벼운 수업용 시작점입니다. 모든 한국어 기사에 가장 우수하다는 의미는 아닙니다. 기본 revision은 `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`으로 고정했습니다.

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-hf.txt
.venv\Scripts\python.exe weather_lab.py generate-article --facts data/results/hourly_facts.json --mode huggingface --output data/results/hf_article.json
```

- Hugging Face API 토큰이나 유료 Hosted Inference를 사용하지 않습니다. 모델 이용 요금은 없지만 컴퓨터/클라우드 GPU 이용료는 별개입니다.
- **최초 실행 시 수 GB 가중치를 다운로드**합니다. 디스크/메모리를 먼저 확인하세요. CPU float32 가중치만 대략 6GB이며 실행 여유 메모리가 더 필요합니다. CPU는 느릴 수 있습니다.
- CUDA는 float16, CPU는 float32를 사용합니다. `trust_remote_code=False`, `use_safetensors=True`로 모델 저장소의 임의 Python 코드를 실행하지 않습니다.
- 다운로드 연결 제한은 기본 30초이며 `HF_HUB_DOWNLOAD_TIMEOUT`/`HF_HUB_ETAG_TIMEOUT`으로 조정합니다. 로컬 추론 전체 실행 시간은 하드 타임아웃으로 보장하지 않습니다.
- `HF_MODEL`, 선택적인 `HF_REVISION` 또는 `--model`로 바꿀 수 있습니다. 사용자 지정 모델의 라이선스/메모리/채팅 템플릿 호환성은 별도 확인이 필요합니다.

### C. openai: 별도 API 요금이 발생하는 초안

기본값은 **[gpt-4.1-mini-2025-04-14](https://developers.openai.com/api/docs/models/gpt-4.1-mini)**입니다. 한국어 지시 기반 짧은 초안에 적합한 경량 모델의 고정 스냅샷을 사용합니다. OpenAI Responses API를 호출합니다.

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-openai.txt
# .env의 OPENAI_API_KEY를 본인 키로 설정한 뒤 실행합니다.
.venv\Scripts\python.exe weather_lab.py generate-article --facts data/results/hourly_facts.json --mode openai --timeout 60 --max-tokens 900 --output data/results/openai_article.json
```

- ChatGPT 구독과 별도인 API 계정, 모델 접근 권한, 과금 설정이 필요합니다. 호출 전에 본인 계정의 요금과 한도를 확인하세요.
- OpenAI로 보내는 항목: 관측소 이름, 기간, 지표·단위·집계 수치, 공개 출처 URL, 해석 한계입니다. 원본 CSV, 로컬 파일명·해시, DB ID는 보내지 않습니다.
- `store=False`로 요청하고 자동 재시도를 끕니다. 이것만으로 모든 서버 로그/보존 정책이 없어지는 것은 아닙니다.
- `--timeout`은 OpenAI 요청의 제한 시간(1~300초), `--max-tokens`는 출력 상한(128~4096)입니다. 비용이 발생한 응답의 저장 오류를 막으려면 출력 경로를 먼저 확인하세요.
- `OPENAI_MODEL` 또는 `--model`로 바꿀 수 있으나 Responses/JSON/temperature 지원 여부를 확인해야 합니다.

### 공통 저장·검토 규칙

모든 방식은 `DRAFT`입니다. JSON에는 기사, 근거 스냅샷, 해시, 모드, 모델/revision, 프롬프트 버전, 보조 검사 결과를 보존하고 같은 위치에 읽기 쉬운 `.txt`를 만듭니다. 기존 출력은 기본적으로 덮어쓰지 않으며 필요한 경우에만 `--overwrite`를 사용합니다.

AI 응답이 비었거나 잘린 경우, JSON 형식 오류, 근거에 없는 아라비아 숫자/비율 표현은 중단합니다. 실패를 템플릿 성공으로 바꾸지 않습니다. **숫자 허용 목록과 관측소 이름 포함 검사는 완전한 사실 검증이 아닙니다.** 숫자 연결 오류, 한글 수사, 잘못된 인과관계, 누락은 사람이 확인해야 합니다. `semantic_fact_check=NOT_PERFORMED`와 `human_review_required=true`를 남깁니다. 외부 모델의 실제 기사 품질은 이번 오프라인 테스트로 평가하지 않았습니다.

DB에 저장된 월 비교 근거를 읽고 생성 이력까지 함께 저장하려면:

```powershell
# 1을 실제 analysis_id로 바꿉니다. mode만 바꾸어 같은 근거로 비교할 수 있습니다.
.venv\Scripts\python.exe weather_lab.py generate-article --analysis-id 1 --mode template --save-to-db --output data/results/db_template.json
```

`--save-to-db`는 `--analysis-id`와 함께만 가능합니다. 템플릿은 `TEMPLATE`, 모델 기사는 `AI` 작성자로 `news_article`에 저장하며 `article_generation`에 당시 근거·모델·검사 결과를 연결합니다. 기사와 생성 이력 저장은 한 트랜잭션입니다. 모델 호출 중 DB 근거가 달라지면 저장을 중단합니다. 파일을 먼저 남기므로 DB 저장 실패 시 API를 재호출하기 전에 저장된 JSON을 확인하세요.

## 6. 기존 사람이 쓴 기사 저장

근거를 보고 본문을 UTF-8 파일에 직접 작성한 뒤 저장합니다.

```powershell
.venv\Scripts\python.exe weather_lab.py save-article --analysis-id 1 --title "직접 작성한 기사 제목" --lead "직접 작성한 리드" --body data/results/article.txt
```

기존대로 `HUMAN/DRAFT`입니다. 모델 초안을 사람 작성 원고로 그대로 가장하여 저장하지 말고, 생성 출처는 `generate-article --save-to-db`로 보존하세요.

## 7. ERD와 SQL 학습 포인트

```mermaid
erDiagram
 station ||--o{ daily_weather : has
 import_batch ||--o{ daily_weather : source
 station ||--o{ analysis_result : analyzed
 analysis_result ||--o{ news_article : evidence
 news_article ||--o| article_generation : generated
```

- PK/FK/UNIQUE/CHECK로 존재하는 근거, 날짜·파일 해시 중복, 작성자/상태/생성 방식을 검사합니다.
- `ON DELETE RESTRICT`로 기사가 연결된 근거 삭제를 막습니다. 실제 SQL 키워드는 `RESTRICT`입니다.
- 기사에서 분석·관측소·생성 이력을 JOIN하여 값과 문장의 연결을 점검합니다.
- 두 기간으로 장기 기후변화, 통계적 유의성, 변화 원인을 단정하지 않습니다.

## 8. 테스트와 검증 범위

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m compileall -q weather_lab.py article_generation.py hourly_weather.py
```

오프라인 테스트 **46개가 통과**했습니다. CSV/월 비교/시간 coverage, 실물 발췌의 24.64℃ 평균, 세 모드 선택, 숫자·형식 검사, API 미설정·타임아웃·불완전 응답, 원본 덮어쓰기 차단·불가능한 coverage 거부·중첩 개인정보 필드 제외·호출 전 출력 경로 검사, HF 입력/출력 토큰 분리와 안전한 로딩 옵션, DB 트랜잭션 계약을 오프라인 검사합니다. 모델 SDK는 mock으로 검사하며 API 요금이나 모델 다운로드가 발생하지 않습니다. 오류 테스트의 가상 수치는 관측 데이터가 아닙니다.

실물 원본 전체의 41일/984시간/21.38℃ 계산과 템플릿 생성은 별도로 실행했습니다. **실제 MySQL 서버 실행, 실제 HF 가중치 추론, 유료 OpenAI 호출은 수행하지 않았습니다.** 사용자 DB에서 스키마/마이그레이션, 동일 파일 재입력, SQL과 JSON 평균 대조, 생성 기사/이력 JOIN을 확인하세요. PostgreSQL 포트는 별도 `postgre` 브랜치의 `weather-history-postgre-lab`에 있습니다.
