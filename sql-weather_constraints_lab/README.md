# 기상 데이터 SQL 실습

[weather_mysql_join_constraints_lab.sql](weather_mysql_join_constraints_lab.sql)을 MySQL Workbench에서 열고 번호 순서대로 구간을 선택하여 실행합니다.

- INNER JOIN, LEFT JOIN, 연결 없는 행 조회, 지역별 집계
- PK, FK, UNIQUE, CHECK, NOT NULL 검증
- ON DELETE CASCADE, SET NULL, RESTRICT 비교

MySQL 8.0.16 이상이 필요합니다. 실습 DB는 `weather_constraints_lab`이며 앱의 `weatherNewsDB`와 구분됩니다.

제약조건 테스트에서 예상 오류로 차단되면 PASS가 표시됩니다. DELIMITER와 CREATE PROCEDURE 구간은 전체를 선택하여 실행하세요. 테스트 변경은 ROLLBACK으로 되돌립니다. 초기 테이블 생성은 한 번만 실행하고, 반복 실습은 해당 테스트 구간만 실행합니다.

[저장소 학습 안내](../README.md)
