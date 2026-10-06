-- Workbench에서 실행하는 비교와 JOIN. 먼저 CSV를 가져오세요.
USE weather_history_lab;
SET @station_id = 108;
SET @baseline_year = 2025;
SET @target_year = 2026;
SET @month = 9;

-- 1. 관측소와 관측값 JOIN: NULL은 누락된 기온이며 0℃와 다릅니다.
SELECT s.station_name, w.observed_date, w.avg_temp_c, b.file_name, b.source_url
FROM daily_weather w JOIN station s ON s.station_id=w.station_id
JOIN import_batch b ON b.batch_id=w.batch_id
WHERE w.station_id=@station_id ORDER BY w.observed_date;

-- 2. 행 수와 유효 기온 수를 구분합니다. AVG는 NULL을 제외합니다.
-- 데이터가 모두 있어야 '전체 월 평균'으로 사용하세요.
SELECT YEAR(observed_date) AS year, COUNT(*) AS row_days,
 COUNT(avg_temp_c) AS valid_days,
 DAY(LAST_DAY(MIN(observed_date))) AS expected_days,
 ROUND(AVG(avg_temp_c),2) AS mean_daily_temperature_c
FROM daily_weather
WHERE station_id=@station_id AND MONTH(observed_date)=@month
 AND YEAR(observed_date) IN (@baseline_year,@target_year)
GROUP BY YEAR(observed_date);

-- 3. 두 해 모두 모든 날짜에 기온이 있을 때만 비교 결과를 반환합니다.
WITH monthly AS (
 SELECT YEAR(observed_date) y, COUNT(*) n, COUNT(avg_temp_c) valid_n,
 DAY(LAST_DAY(MIN(observed_date))) expected_n, AVG(avg_temp_c) mean_temp
 FROM daily_weather WHERE station_id=@station_id AND MONTH(observed_date)=@month
 AND YEAR(observed_date) IN (@baseline_year,@target_year)
 GROUP BY YEAR(observed_date)
)
SELECT b.y baseline_year,t.y target_year,ROUND(b.mean_temp,2) baseline_mean_c,
 ROUND(t.mean_temp,2) target_mean_c,ROUND(t.mean_temp-b.mean_temp,2) difference_c
FROM monthly b JOIN monthly t ON b.y=@baseline_year AND t.y=@target_year
WHERE b.valid_n=b.expected_n AND t.valid_n=t.expected_n;

-- 4. 기사 → 분석 → 관측소 JOIN으로 기사 근거를 확인합니다.
SELECT a.article_id,a.title,a.status,s.station_name,r.baseline_year,
 r.target_year,r.target_month,r.fact_sheet
FROM news_article a JOIN analysis_result r ON r.analysis_id=a.analysis_id
JOIN station s ON s.station_id=r.station_id;
