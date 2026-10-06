# 한국어 학습 주석 추가본

기준: journal-izm/sql_study main 8172fee5b9f754952b3152c73d35569d318a7321.
네 폴더의 현재 GitHub 소스를 읽고 18개 파일에 주석 261개 블록을 추가했습니다.
실행 코드·SQL·모델·API·화면 기능은 그대로 유지했습니다.

설명 범위: 요청/응답, JSON과 fetch, PUT 전체 교체/PATCH 부분 수정,
서버 입력 검사와 DB FK 검사, SQL 매개변수 바인딩, PK/UNIQUE/CHECK,
CASCADE/RESTRICT, CSV 인코딩·중복·결측, 월 평균·기간 비교,
commit/rollback/finally, 분석과 기사 근거 연결, 테스트 목적.

## 적용

ZIP의 네 폴더를 저장소 루트의 같은 이름 폴더와 비교하고 수정한 소스 파일을 반영합니다.
원본 CSV/결과물/.env/node_modules는 포함하지 않았습니다. 로컬에 있는 파일은 유지하세요.
대안으로 저장소 루트에서 패치 검사 후 적용할 수 있습니다.

```powershell
git apply --check sql-study-korean-comments.patch
git apply sql-study-korean-comments.patch
git diff
git add weather-history-mysql-lab weather-history-node-mysql-lab openweather-node-mysql-crud-constraints-app openweather-fastapi-mysql-crud-constraints-app
git commit -m "docs: add Korean teaching comments to weather labs and CRUD apps"
git push origin main
```

기준 커밋 이후 로컬/원격 코드가 바뀌었다면 git apply --check가 실패할 수 있습니다.
실패 시 덮어쓰지 말고 파일별 차이를 확인하세요.

## 확인

원래 코드 줄이 삭제·수정되지 않고 주석만 추가되었음을 확인했습니다.
Python AST 동일성, Node/HTML 내 JavaScript 문법 검사 통과.
과거 기상 실습 Python 7개 + Node.js 7개 기존 테스트 통과.
실제 MySQL/API 호출과 브라우저 화면 실행을 추가로 검증하지 않았습니다.
GitHub 쓰기는 연결 앱 403(Resource not accessible by integration)으로 거부되어 반영하지 못했습니다.
