-- MySQL 8.0.16 이상 필요: CHECK 실제 적용
-- 기존 테이블은 CREATE IF NOT EXISTS로 변경되지 않습니다. migration_constraints.sql 참고
-- =========================================================
-- OpenWeather + MySQL + 기사 CRUD 학습용 SQL
-- =========================================================

-- 실습 DB를 생성합니다. 기존 데이터베이스나 테이블을 삭제하는 명령은 아닙니다.
CREATE DATABASE IF NOT EXISTS weatherNewsDB
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- 이후 명령을 적용할 DB를 선택합니다. Workbench에서 선택 DB를 확인하세요.
USE weatherNewsDB;

-- 엔터티별 테이블을 정의합니다. CREATE IF NOT EXISTS는 이미 존재하는 테이블의 구조를 수정하지 않습니다.
CREATE TABLE IF NOT EXISTS weather_observation (
    weather_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    city_code VARCHAR(20) NOT NULL,
    region_name VARCHAR(30) NOT NULL,
    city_name VARCHAR(60),
    temperature DECIMAL(5,2) NOT NULL,
    feels_like DECIMAL(5,2),
    humidity INT,
    wind_speed DECIMAL(6,2),
    description VARCHAR(100),
    observed_at DATETIME NOT NULL,
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- 같은 도시·관측 시각의 중복 저장 금지
    CONSTRAINT uq_weather_city_time UNIQUE (city_code, observed_at),
    -- CHECK는 새로 저장/수정되는 값이 조건을 만족하는지 검사합니다. NULL 여부는 NOT NULL과 함께 설계합니다.
    CONSTRAINT chk_weather_humidity CHECK (humidity BETWEEN 0 AND 100),
    -- CHECK는 새로 저장/수정되는 값이 조건을 만족하는지 검사합니다. NULL 여부는 NOT NULL과 함께 설계합니다.
    CONSTRAINT chk_weather_wind CHECK (wind_speed >= 0)
) ENGINE=InnoDB;

-- 엔터티별 테이블을 정의합니다. CREATE IF NOT EXISTS는 이미 존재하는 테이블의 구조를 수정하지 않습니다.
CREATE TABLE IF NOT EXISTS news_article (
    article_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    weather_id BIGINT NULL, -- 연결 없이 작성할 수도 있음
    source_region VARCHAR(30),
    title VARCHAR(200) NOT NULL,
    lead_text TEXT,
    body_text TEXT,
    status ENUM('DRAFT','REVIEW','APPROVED','REJECTED') NOT NULL DEFAULT 'DRAFT',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    -- CHECK는 새로 저장/수정되는 값이 조건을 만족하는지 검사합니다. NULL 여부는 NOT NULL과 함께 설계합니다.
    CONSTRAINT chk_article_title CHECK (CHAR_LENGTH(TRIM(title)) > 0),
    -- 학습용: 관측값 삭제 시 이 관측값에 연결된 기사도 삭제
    CONSTRAINT fk_article_weather FOREIGN KEY (weather_id)
      REFERENCES weather_observation(weather_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- C
INSERT INTO news_article
(source_region, title, lead_text, body_text, status)
VALUES ('서울', '서울 기상 데이터 분석', '학습용 리드문', '학습용 본문', 'DRAFT');

-- R
SELECT * FROM news_article ORDER BY article_id DESC;

-- U
UPDATE news_article
SET title='수정된 기사 제목', status='REVIEW'
WHERE article_id=1;

-- D
-- DELETE FROM news_article WHERE article_id=1;

-- 지역별 집계
SELECT
    region_name,
    COUNT(*) AS observation_count,
    ROUND(AVG(temperature), 1) AS avg_temperature,
    MAX(temperature) AS max_temperature,
    MIN(temperature) AS min_temperature,
    ROUND(AVG(humidity), 1) AS avg_humidity,
    MAX(wind_speed) AS max_wind_speed
FROM weather_observation
GROUP BY region_name
ORDER BY avg_temperature DESC;
