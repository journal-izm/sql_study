-- 기존 원본 DB용 1회 마이그레이션. 재실행하지 마세요.
-- 먼저 백업하고 아래 조회 결과를 확인하여 중복/NULL/잘못된 값을 수정하세요.
-- 이 스크립트는 기존 행을 삭제하거나 자동으로 기사와 관측값을 연결하지 않습니다.
-- 이후 명령을 적용할 DB를 선택합니다. Workbench에서 선택 DB를 확인하세요.
USE weatherNewsDB;
SELECT city_code, observed_at, COUNT(*) FROM weather_observation
GROUP BY city_code, observed_at HAVING COUNT(*) > 1;
SELECT * FROM weather_observation WHERE observed_at IS NULL
 OR humidity NOT BETWEEN 0 AND 100 OR wind_speed < 0;
SELECT * FROM news_article WHERE title IS NULL OR TRIM(title) = '' OR status IS NULL;
-- 위 문제를 해결한 뒤 다음 ALTER를 실행하세요. MySQL DDL은 자동 커밋됩니다.
-- 기존 테이블 구조를 변경합니다. 현재 데이터가 새 제약을 위반하면 적용 전에 데이터를 정리해야 합니다.
ALTER TABLE weather_observation
 MODIFY observed_at DATETIME NOT NULL,
 ADD CONSTRAINT uq_weather_city_time UNIQUE (city_code, observed_at),
 ADD CONSTRAINT chk_weather_humidity CHECK (humidity BETWEEN 0 AND 100),
 ADD CONSTRAINT chk_weather_wind CHECK (wind_speed >= 0);
-- 기존 테이블 구조를 변경합니다. 현재 데이터가 새 제약을 위반하면 적용 전에 데이터를 정리해야 합니다.
ALTER TABLE news_article
 ADD COLUMN weather_id BIGINT NULL AFTER article_id,
 MODIFY status ENUM('DRAFT','REVIEW','APPROVED','REJECTED') NOT NULL DEFAULT 'DRAFT',
 ADD CONSTRAINT chk_article_title CHECK (CHAR_LENGTH(TRIM(title)) > 0),
 ADD CONSTRAINT fk_article_weather FOREIGN KEY (weather_id)
 REFERENCES weather_observation(weather_id) ON DELETE CASCADE;
