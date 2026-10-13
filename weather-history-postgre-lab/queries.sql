-- PostgreSQL: weather_history_lab에 연결한 같은 Query Tool/psql 세션에서 실행합니다.
-- 임시 VIEW는 이 세션에서만 유지됩니다. 실제 자료에 맞춰 아래 네 값을 수정하세요.
CREATE OR REPLACE TEMP VIEW lab_params AS
SELECT 108::integer AS station_id, 2025::integer AS baseline_year,
       2026::integer AS target_year, 9::integer AS target_month;

-- 1. 관측소·관측·출처 JOIN. 시간 CSV는 이 테이블에 넣지 않습니다.
SELECT s.station_name,w.observed_date,w.avg_temp_c,b.file_name,b.source_url
FROM daily_weather w JOIN station s ON s.station_id=w.station_id
JOIN import_batch b ON b.batch_id=w.batch_id
CROSS JOIN lab_params p
WHERE w.station_id=p.station_id ORDER BY w.observed_date;

-- 2. 행 수와 NULL을 제외한 기온 수를 구분합니다. 부분 평균은 월 평균 기사에 쓰지 않습니다.
SELECT EXTRACT(YEAR FROM observed_date)::integer AS year,COUNT(*) AS row_days,
 COUNT(avg_temp_c) AS valid_days,
 EXTRACT(DAY FROM (DATE_TRUNC('month',MIN(observed_date))+INTERVAL '1 month'-INTERVAL '1 day'))::integer AS expected_days,
 ROUND(AVG(avg_temp_c),2) AS mean_daily_temperature_c
FROM daily_weather CROSS JOIN lab_params p
WHERE daily_weather.station_id=p.station_id
 AND EXTRACT(MONTH FROM observed_date)=p.target_month
 AND EXTRACT(YEAR FROM observed_date) IN (p.baseline_year,p.target_year)
GROUP BY EXTRACT(YEAR FROM observed_date);

-- 3. 두 해 모두 완전한 달일 때만 월 비교를 반환합니다.
WITH monthly AS (
 SELECT EXTRACT(YEAR FROM observed_date)::integer AS y,COUNT(*) AS n,
 COUNT(avg_temp_c) AS valid_n,
 EXTRACT(DAY FROM (DATE_TRUNC('month',MIN(observed_date))+INTERVAL '1 month'-INTERVAL '1 day'))::integer AS expected_n,
 AVG(avg_temp_c) AS mean_temp
 FROM daily_weather CROSS JOIN lab_params p
 WHERE daily_weather.station_id=p.station_id
  AND EXTRACT(MONTH FROM observed_date)=p.target_month
  AND EXTRACT(YEAR FROM observed_date) IN (p.baseline_year,p.target_year)
 GROUP BY EXTRACT(YEAR FROM observed_date)
)
SELECT b.y AS baseline_year,t.y AS target_year,ROUND(b.mean_temp,2) AS baseline_mean_c,
 ROUND(t.mean_temp,2) AS target_mean_c,ROUND(t.mean_temp-b.mean_temp,2) AS difference_c
FROM monthly b CROSS JOIN monthly t CROSS JOIN lab_params p
WHERE b.y=p.baseline_year AND t.y=p.target_year
 AND b.valid_n=b.expected_n AND t.valid_n=t.expected_n;

-- 4. 기사 → 분석 → 관측소 JOIN. JSONB 근거를 그대로 조회합니다.
SELECT a.article_id,a.title,a.status,s.station_name,r.baseline_year,r.target_year,
 r.target_month,r.fact_sheet
FROM news_article a JOIN analysis_result r ON r.analysis_id=a.analysis_id
JOIN station s ON s.station_id=r.station_id;

-- 5. 생성 방식과 모델·검사 결과. DRAFT는 검증 통과 상태가 아닙니다.
SELECT a.article_id,a.title,a.author_type,a.status,g.generation_mode,g.model_name,
 g.prompt_version,g.facts_sha256,g.validation_checks
FROM news_article a LEFT JOIN article_generation g ON g.article_id=a.article_id
ORDER BY a.article_id;
