-- MySQL Workbench 실습 / MySQL 8.0.16 이상
-- 기존 weatherNewsDB와 분리한 실습 DB. DROP 문은 포함하지 않음.
-- 처음 한 번 실행. 같은 DB에서 재실행하면 테이블 중복 오류가 발생합니다.
SELECT VERSION();
CREATE DATABASE IF NOT EXISTS weather_constraints_lab CHARACTER SET utf8mb4;
USE weather_constraints_lab;

-- 1. PK, UNIQUE, CHECK, NOT NULL
CREATE TABLE weather_observation (
 weather_id BIGINT AUTO_INCREMENT PRIMARY KEY,
 city_code VARCHAR(20) NOT NULL,
 region_name VARCHAR(30) NOT NULL,
 temperature DECIMAL(5,2) NOT NULL,
 humidity INT NOT NULL,
 wind_speed DECIMAL(6,2) NOT NULL,
 observed_at DATETIME NOT NULL,
 CONSTRAINT uq_city_time UNIQUE(city_code, observed_at),
 CONSTRAINT chk_humidity CHECK(humidity BETWEEN 0 AND 100),
 CONSTRAINT chk_wind CHECK(wind_speed >= 0)
) ENGINE=InnoDB;

CREATE TABLE news_article (
 article_id BIGINT AUTO_INCREMENT PRIMARY KEY,
 weather_id BIGINT NULL,
 title VARCHAR(200) NOT NULL,
 CONSTRAINT chk_title CHECK(CHAR_LENGTH(TRIM(title)) > 0),
 CONSTRAINT fk_article_weather FOREIGN KEY(weather_id)
 REFERENCES weather_observation(weather_id) ON DELETE CASCADE
) ENGINE=InnoDB;

INSERT INTO weather_observation
(weather_id, city_code, region_name, temperature, humidity, wind_speed, observed_at)
VALUES (1,'seoul','서울',25,60,2,'2026-10-01 09:00:00'),
       (2,'busan','부산',27,70,3,'2026-10-01 09:00:00'),
       (3,'seoul','서울',24,55,1,'2026-10-02 09:00:00'),
       (4,'jeju','제주',26,80,4,'2026-10-01 09:00:00');
INSERT INTO news_article(article_id,weather_id,title)
VALUES (1,1,'서울 기온 기사'),(2,1,'서울 습도 기사'),
       (3,2,'부산 기상 기사'),(4,NULL,'관측값 연결 없는 기사');
-- 모두 가상 데이터. 관측값 1에는 기사 2개, 관측값 3·4에는 기사 없음.

-- 상황: 기자가 기사와 그 근거가 된 기온을 함께 확인하려고 합니다.
-- ON은 두 테이블에서 연결할 열을 지정합니다. a와 w는 테이블 별칭입니다.
-- 연결이 없는 기사는 INNER JOIN 결과에 포함되지 않습니다.
-- 2. INNER JOIN: 연결된 기사 3행만 조회
SELECT a.article_id,a.title,w.region_name,w.temperature,w.observed_at
FROM news_article a INNER JOIN weather_observation w
ON a.weather_id=w.weather_id ORDER BY a.article_id;

-- 상황: 아직 관측값을 연결하지 않은 기사까지 전체 기사 목록을 확인합니다.
-- 왼쪽(news_article)의 모든 행을 유지하고 연결되는 오른쪽 값이 없으면 NULL을 표시합니다.
-- 3. LEFT JOIN: 기사 4행 유지. 연결 없는 기사의 관측 열은 NULL
SELECT a.article_id,a.title,w.region_name,w.temperature
FROM news_article a LEFT JOIN weather_observation w
ON a.weather_id=w.weather_id ORDER BY a.article_id;

-- 상황: 수집한 관측값 중 기사로 활용한 자료와 아직 활용하지 않은 자료를 구분합니다.
-- 4. 반대 방향 LEFT JOIN: 관측값별 기사 수 = 2,1,0,0
-- COUNT(*) 대신 COUNT(a.article_id): 기사 없는 관측값은 0으로 계산
SELECT w.weather_id,w.region_name,COUNT(a.article_id) AS article_count
FROM weather_observation w LEFT JOIN news_article a
ON w.weather_id=a.weather_id
GROUP BY w.weather_id,w.region_name ORDER BY w.weather_id;

-- 5. 연결이 없는 행 찾기
-- 첫 쿼리: 근거 연결이 없는 기사 → 기사 4번.
-- 둘째 쿼리: 어떤 기사도 참조하지 않는 관측값 → 관측값 3번과 4번.
SELECT a.* FROM news_article a LEFT JOIN weather_observation w
ON a.weather_id=w.weather_id WHERE w.weather_id IS NULL;
SELECT w.* FROM weather_observation w LEFT JOIN news_article a
ON w.weather_id=a.weather_id WHERE a.article_id IS NULL;

-- 상황: 서울의 두 관측값(25℃,24℃) 평균은 24.5℃입니다.
-- 기사와 먼저 JOIN하면 25℃ 관측값이 기사 2개 때문에 두 번 나타납니다.
-- 그 상태의 평균은 24.7℃로 바뀌므로 관측 테이블에서 직접 계산합니다.
-- 6. 지역별 집계. JOIN 후 평균을 구하면 기사 수 때문에 관측값이 반복될 수 있음.
-- 관측 데이터 자체에서 집계하여 중복 가중을 피함.
SELECT region_name,COUNT(*) AS observation_count,
 ROUND(AVG(temperature),1) AS avg_temperature,
 MAX(temperature) AS max_temperature,MIN(temperature) AS min_temperature
FROM weather_observation GROUP BY region_name ORDER BY region_name;

-- 7. 생성된 제약조건 확인
-- SHOW CREATE TABLE: 서버가 실제로 저장한 테이블 정의를 확인합니다.
-- information_schema: 제약 이름과 종류를 목록으로 조회합니다.
SHOW CREATE TABLE weather_observation;
SHOW CREATE TABLE news_article;
SELECT TABLE_NAME,CONSTRAINT_NAME,CONSTRAINT_TYPE
FROM information_schema.TABLE_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA=DATABASE() ORDER BY TABLE_NAME,CONSTRAINT_TYPE;

-- 8. 실패 검증 도우미: 예상 오류를 잡아 뒤의 실습도 계속 실행
-- DELIMITER 구간 전체를 선택해 실행하세요. 실제 DB 오류 번호를 비교합니다.
DELIMITER $$
CREATE PROCEDURE expect_error(IN test_name VARCHAR(100), IN sql_text TEXT, IN expected_code INT)
BEGIN
 DECLARE actual_code INT DEFAULT 0;
 DECLARE actual_message TEXT;
 DECLARE stmt_ready BOOLEAN DEFAULT FALSE;
 DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
 BEGIN
  GET DIAGNOSTICS CONDITION 1 actual_code=MYSQL_ERRNO,actual_message=MESSAGE_TEXT;
 END;
 SET @lab_sql=sql_text;
 PREPARE lab_stmt FROM @lab_sql;
 IF actual_code=0 THEN
  SET stmt_ready=TRUE;
  EXECUTE lab_stmt;
 END IF;
 IF stmt_ready THEN DEALLOCATE PREPARE lab_stmt; END IF;
 SELECT test_name AS test,
 IF(actual_code=expected_code,'PASS','FAIL') AS result,
 expected_code,actual_code,actual_message;
END$$
DELIMITER ;

-- PASS는 잘못된 입력이 예상 오류로 차단되었다는 뜻입니다. FAIL이면 오류 번호를 확인하세요.
-- 테스트 변경은 마지막 ROLLBACK. AUTO_INCREMENT 번호는 되돌아가지 않을 수 있음.
START TRANSACTION;
-- 상황: 이미 있는 관측 ID 1을 다시 입력 → PK가 중복을 거부합니다.
CALL expect_error('PK 중복',
 'INSERT INTO weather_observation VALUES(1,"test","테스트",20,50,1,"2026-10-03")',1062);
-- 상황: 서울의 동일 관측 시각 자료를 재수집 → 복합 UNIQUE가 중복을 거부합니다.
-- city_code만 UNIQUE라면 서울의 다음 날 자료도 저장할 수 없어 조합으로 설정했습니다.
CALL expect_error('복합 UNIQUE 중복',
 'INSERT INTO weather_observation(city_code,region_name,temperature,humidity,wind_speed,observed_at) VALUES("seoul","서울",25,60,2,"2026-10-01 09:00:00")',1062);
-- 상황: 저장된 적 없는 관측 ID 999999를 기사 근거로 지정 → FK가 연결을 거부합니다.
CALL expect_error('FK 없는 관측값 연결',
 'INSERT INTO news_article(weather_id,title) VALUES(999999,"잘못된 연결")',1452);
-- 상황: 습도를 101%로 수정 → CHECK 범위 밖이므로 거부합니다. 기존 60%는 유지됩니다.
CALL expect_error('CHECK 습도 범위',
 'UPDATE weather_observation SET humidity=101 WHERE weather_id=1',3819);
-- 상황: 풍속에 -1 입력 → 0 이상 조건을 만족하지 못합니다.
CALL expect_error('CHECK 음수 풍속',
 'UPDATE weather_observation SET wind_speed=-1 WHERE weather_id=1',3819);
-- 상황: 공백만 있는 제목 → TRIM으로 공백 제거 후 길이가 0이므로 거부합니다.
CALL expect_error('CHECK 빈 제목',
 'INSERT INTO news_article(title) VALUES("   ")',3819);
-- 상황: 제목 자체를 NULL로 입력 → NOT NULL이 거부합니다. 빈 문자열과 NULL은 다릅니다.
CALL expect_error('NOT NULL',
 'INSERT INTO news_article(title) VALUES(NULL)',1048);
-- 정상 입력: 같은 도시 + 다른 시각, FK NULL, 같은 제목의 다른 기사 허용
INSERT INTO weather_observation(city_code,region_name,temperature,humidity,wind_speed,observed_at)
VALUES('seoul','서울',23,50,1,'2026-10-03 09:00:00');
INSERT INTO news_article(weather_id,title) VALUES(NULL,'서울 기온 기사');
SELECT '정상 입력 확인' AS test,COUNT(*) AS article_count FROM news_article;
ROLLBACK;

-- 상황: 관측값 1을 삭제하면 이를 근거로 삼는 기사 1·2도 자동 삭제됩니다.
-- 실습 후 ROLLBACK으로 부모와 자식을 모두 복원합니다.
-- 9. CASCADE: 부모 삭제 → 연결된 기사 2개 삭제
START TRANSACTION;
DELETE FROM weather_observation WHERE weather_id=1;
SELECT 'CASCADE: 기사 1,2가 사라짐' AS test,article_id,weather_id,title
FROM news_article ORDER BY article_id;
ROLLBACK;
-- 자식 삭제는 부모를 삭제하지 않음
START TRANSACTION;
DELETE FROM news_article WHERE article_id=1;
SELECT '기사 삭제 후 관측값 1 유지' AS test,w.*
FROM weather_observation w WHERE weather_id=1;
ROLLBACK;

-- CASCADE를 설정한 기존 FK는 그대로 두고, 비교용 자식 테이블에 다른 정책을 설정합니다.
-- 한 FK에 세 정책을 동시에 설정하는 것은 아닙니다.
-- 10. SET NULL / RESTRICT 비교: 별도 자식 테이블
CREATE TABLE article_set_null (
 article_id INT PRIMARY KEY,
 weather_id BIGINT NULL,
 CONSTRAINT fk_set_null FOREIGN KEY(weather_id)
 REFERENCES weather_observation(weather_id) ON DELETE SET NULL
) ENGINE=InnoDB;
CREATE TABLE article_restrict (
 article_id INT PRIMARY KEY,
 weather_id BIGINT NOT NULL,
 CONSTRAINT fk_restrict FOREIGN KEY(weather_id)
 REFERENCES weather_observation(weather_id) ON DELETE RESTRICT
) ENGINE=InnoDB;
INSERT INTO article_set_null VALUES(1,3);
INSERT INTO article_restrict VALUES(1,4);

START TRANSACTION;
-- 상황: 관측값 3은 없애되 비교용 기사 행은 유지하려고 합니다.
-- article_set_null.weather_id만 NULL로 바뀌고 article_id=1은 남습니다.
DELETE FROM weather_observation WHERE weather_id=3;
SELECT 'SET NULL: 기사 유지, weather_id=NULL' AS test,t.* FROM article_set_null t;
ROLLBACK;

START TRANSACTION;
-- 상황: 비교용 기사에서 참조 중인 관측값 4의 삭제를 막아 근거를 보존합니다.
CALL expect_error('RESTRICT: 참조 기사 있으면 부모 삭제 차단',
 'DELETE FROM weather_observation WHERE weather_id=4',1451);
SELECT '부모 유지' AS test,w.* FROM weather_observation w WHERE weather_id=4;
-- 먼저 자식을 삭제하면 부모 삭제 가능
DELETE FROM article_restrict WHERE article_id=1;
DELETE FROM weather_observation WHERE weather_id=4;
SELECT '자식 제거 후 부모 삭제: 0행' AS test,w.* FROM weather_observation w WHERE weather_id=4;
ROLLBACK;

-- 11. 최종 확인: 원본 실습 행 유지. 부모 4, 기사 4
SELECT COUNT(*) AS weather_count FROM weather_observation;
SELECT COUNT(*) AS article_count FROM news_article;
-- 같은 DB에서 검증을 반복하려면 8번의 CREATE PROCEDURE는 제외하고
-- START TRANSACTION 이후의 CALL~ROLLBACK 구간을 실행하세요.
-- PK는 NOT NULL이며 UNIQUE는 NULL을 허용할 수 있음.
-- CHECK도 NULL 판정을 허용하므로 필수값은 NOT NULL을 함께 지정.
-- SET NULL은 nullable FK 필요. 올바른 문법: RESTRICT (RESTRICTED 아님).
