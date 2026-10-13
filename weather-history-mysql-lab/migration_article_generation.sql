-- 기존 버전 사용자만 한 번 실행합니다. 실행 전 실습 DB를 백업하세요.
-- 신규 사용자는 schema.sql만 실행합니다. 기존 관측/기사 행은 삭제하지 않습니다.
USE weather_history_lab;
ALTER TABLE news_article DROP CHECK ck_article_author;
ALTER TABLE news_article ADD CONSTRAINT ck_article_author
 CHECK (author_type IN ('HUMAN','TEMPLATE','AI'));

-- 생성 방식과 기사 작성 당시 근거/검사 결과를 함께 보존합니다.
CREATE TABLE IF NOT EXISTS article_generation (
 article_id BIGINT PRIMARY KEY,
 generation_mode VARCHAR(16) NOT NULL,
 model_name VARCHAR(255) NULL,
 prompt_version VARCHAR(64) NOT NULL,
 fact_snapshot JSON NOT NULL,
 facts_sha256 CHAR(64) NOT NULL,
 validation_checks JSON NOT NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT fk_generation_article FOREIGN KEY (article_id) REFERENCES news_article(article_id) ON DELETE RESTRICT,
 CONSTRAINT ck_generation_mode CHECK (generation_mode IN ('template','huggingface','openai'))
);
