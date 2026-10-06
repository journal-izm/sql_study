-- MySQL Workbench에서 전체 실행. MySQL 8.0.16 이상(CHECK 적용).
-- 기존 날씨 앱과 분리된 DB이며 기존 테이블을 삭제하지 않습니다.
-- 실습 DB를 생성합니다. 기존 데이터베이스나 테이블을 삭제하는 명령은 아닙니다.
CREATE DATABASE IF NOT EXISTS weather_history_lab CHARACTER SET utf8mb4;
-- 이후 명령을 적용할 DB를 선택합니다. Workbench에서 선택 DB를 확인하세요.
USE weather_history_lab;

-- 관측소 한 곳에 여러 날짜의 관측값이 연결됩니다.
-- 엔터티별 테이블을 정의합니다. CREATE IF NOT EXISTS는 이미 존재하는 테이블의 구조를 수정하지 않습니다.
CREATE TABLE IF NOT EXISTS station (
 station_id INT PRIMARY KEY COMMENT 'CSV 지점 코드',
 station_name VARCHAR(100) NOT NULL,
 -- CHECK는 새로 저장/수정되는 값이 조건을 만족하는지 검사합니다. NULL 여부는 NOT NULL과 함께 설계합니다.
 CONSTRAINT ck_station_id CHECK (station_id > 0),
 -- CHECK는 새로 저장/수정되는 값이 조건을 만족하는지 검사합니다. NULL 여부는 NOT NULL과 함께 설계합니다.
 CONSTRAINT ck_station_name CHECK (CHAR_LENGTH(TRIM(station_name)) > 0)
);
-- 파일명뿐 아니라 해시와 출처를 저장하여 어떤 원본을 사용했는지 확인합니다.
-- 엔터티별 테이블을 정의합니다. CREATE IF NOT EXISTS는 이미 존재하는 테이블의 구조를 수정하지 않습니다.
CREATE TABLE IF NOT EXISTS import_batch (
 batch_id BIGINT AUTO_INCREMENT PRIMARY KEY,
 file_name VARCHAR(255) NOT NULL,
 sha256 CHAR(64) NOT NULL UNIQUE,
 source_url VARCHAR(1000) NOT NULL,
 imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- 엔터티별 테이블을 정의합니다. CREATE IF NOT EXISTS는 이미 존재하는 테이블의 구조를 수정하지 않습니다.
CREATE TABLE IF NOT EXISTS daily_weather (
 weather_id BIGINT AUTO_INCREMENT PRIMARY KEY,
 station_id INT NOT NULL,
 observed_date DATE NOT NULL COMMENT '한국 현지 관측 날짜',
 avg_temp_c DECIMAL(5,2) NULL COMMENT '일평균기온, 결측은 NULL',
 batch_id BIGINT NOT NULL,
 -- 복합 UNIQUE: 괄호 안 열의 조합이 같으면 중복으로 거부합니다. 각각의 열은 반복될 수 있습니다.
 UNIQUE KEY uq_station_date (station_id, observed_date),
 -- FK는 부모 ID의 존재를 검사합니다. RESTRICT는 자식이 연결된 부모 삭제를 막아 근거를 보존합니다.
 CONSTRAINT fk_weather_station FOREIGN KEY (station_id) REFERENCES station(station_id) ON DELETE RESTRICT,
 -- FK는 부모 ID의 존재를 검사합니다. RESTRICT는 자식이 연결된 부모 삭제를 막아 근거를 보존합니다.
 CONSTRAINT fk_weather_batch FOREIGN KEY (batch_id) REFERENCES import_batch(batch_id) ON DELETE RESTRICT
);
-- 분석 결과의 스냅샷: 이후 관측 데이터가 바뀌어도 기사 작성 당시 결과를 보존합니다.
-- 엔터티별 테이블을 정의합니다. CREATE IF NOT EXISTS는 이미 존재하는 테이블의 구조를 수정하지 않습니다.
CREATE TABLE IF NOT EXISTS analysis_result (
 analysis_id BIGINT AUTO_INCREMENT PRIMARY KEY,
 station_id INT NOT NULL,
 baseline_year SMALLINT NOT NULL,
 target_year SMALLINT NOT NULL,
 target_month TINYINT NOT NULL,
 fact_sheet JSON NOT NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 -- FK는 부모 ID의 존재를 검사합니다. RESTRICT는 자식이 연결된 부모 삭제를 막아 근거를 보존합니다.
 CONSTRAINT fk_analysis_station FOREIGN KEY (station_id) REFERENCES station(station_id) ON DELETE RESTRICT,
 -- CHECK는 새로 저장/수정되는 값이 조건을 만족하는지 검사합니다. NULL 여부는 NOT NULL과 함께 설계합니다.
 CONSTRAINT ck_analysis_month CHECK (target_month BETWEEN 1 AND 12),
 -- CHECK는 새로 저장/수정되는 값이 조건을 만족하는지 검사합니다. NULL 여부는 NOT NULL과 함께 설계합니다.
 CONSTRAINT ck_analysis_years CHECK (baseline_year BETWEEN 1904 AND 9999 AND target_year BETWEEN 1904 AND 9999 AND baseline_year <> target_year)
);
-- 엔터티별 테이블을 정의합니다. CREATE IF NOT EXISTS는 이미 존재하는 테이블의 구조를 수정하지 않습니다.
CREATE TABLE IF NOT EXISTS news_article (
 article_id BIGINT AUTO_INCREMENT PRIMARY KEY,
 analysis_id BIGINT NOT NULL,
 title VARCHAR(200) NOT NULL,
 lead_text TEXT NULL,
 body_text LONGTEXT NOT NULL,
 author_type VARCHAR(10) NOT NULL DEFAULT 'HUMAN',
 status VARCHAR(10) NOT NULL DEFAULT 'DRAFT',
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 -- FK는 부모 ID의 존재를 검사합니다. RESTRICT는 자식이 연결된 부모 삭제를 막아 근거를 보존합니다.
 CONSTRAINT fk_article_analysis FOREIGN KEY (analysis_id) REFERENCES analysis_result(analysis_id) ON DELETE RESTRICT,
 -- CHECK는 새로 저장/수정되는 값이 조건을 만족하는지 검사합니다. NULL 여부는 NOT NULL과 함께 설계합니다.
 CONSTRAINT ck_article_title CHECK (CHAR_LENGTH(TRIM(title)) > 0),
 -- CHECK는 새로 저장/수정되는 값이 조건을 만족하는지 검사합니다. NULL 여부는 NOT NULL과 함께 설계합니다.
 CONSTRAINT ck_article_body CHECK (CHAR_LENGTH(TRIM(body_text)) > 0),
 -- CHECK는 새로 저장/수정되는 값이 조건을 만족하는지 검사합니다. NULL 여부는 NOT NULL과 함께 설계합니다.
 CONSTRAINT ck_article_author CHECK (author_type IN ('HUMAN','AI')),
 -- CHECK는 새로 저장/수정되는 값이 조건을 만족하는지 검사합니다. NULL 여부는 NOT NULL과 함께 설계합니다.
 CONSTRAINT ck_article_status CHECK (status IN ('DRAFT','REVIEW','APPROVED','REJECTED'))
);
-- RESTRICT: 기사 근거인 분석과 관측소의 실수 삭제를 막습니다.
-- 정확한 문법은 ON DELETE RESTRICT입니다.
