-- Workbench에서 실행하는 비교와 JOIN. 먼저 CSV를 가져오세요.
-- 이후 명령을 적용할 DB를 선택합니다. Workbench에서 선택 DB를 확인하세요.
USE weather_history_lab;
-- Workbench 세션 변수입니다. 관측소/기간을 바꾸어 같은 비교 SQL을 재사용합니다.
SET @station_id = 108;
-- Workbench 세션 변수입니다. 관측소/기간을 바꾸어 같은 비교 SQL을 재사용합니다.
SET @baseline_year = 2025;
-- Workbench 세션 변수입니다. 관측소/기간을 바꾸어 같은 비교 SQL을 재사용합니다.
SET @target_year = 2026;
-- Workbench 세션 변수입니다. 관측소/기간을 바꾸어 같은 비교 SQL을 재사용합니다.
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
-- 연도별로 그룹을 분리합니다. COUNT(*)는 행 수, COUNT(기온)은 NULL 제외 유효값 수입니다.
GROUP BY YEAR(observed_date);

-- 3. 두 해 모두 모든 날짜에 기온이 있을 때만 비교 결과를 반환합니다.
-- CTE로 월별 집계 결과에 이름을 붙여 두 기간을 JOIN합니다.
WITH monthly AS (
 SELECT YEAR(observed_date) y, COUNT(*) n, COUNT(avg_temp_c) valid_n,
 DAY(LAST_DAY(MIN(observed_date))) expected_n, AVG(avg_temp_c) mean_temp
 FROM daily_weather WHERE station_id=@station_id AND MONTH(observed_date)=@month
 AND YEAR(observed_date) IN (@baseline_year,@target_year)
 -- 연도별로 그룹을 분리합니다. COUNT(*)는 행 수, COUNT(기온)은 NULL 제외 유효값 수입니다.
 GROUP BY YEAR(observed_date)
)
SELECT b.y baseline_year,t.y target_year,ROUND(b.mean_temp,2) baseline_mean_c,
 ROUND(t.mean_temp,2) target_mean_c,ROUND(t.mean_temp-b.mean_temp,2) difference_c
-- 같은 집계 결과를 두 별칭으로 연결합니다. b=기준 해, t=대상 해입니다.
FROM monthly b JOIN monthly t ON b.y=@baseline_year AND t.y=@target_year
-- 두 월의 유효 기온 개수가 전체 일수와 같을 때만 비교 결과를 반환합니다.
WHERE b.valid_n=b.expected_n AND t.valid_n=t.expected_n;

-- 4. 기사 → 분석 → 관측소 JOIN으로 기사 근거를 확인합니다.
SELECT a.article_id,a.title,a.status,s.station_name,r.baseline_year,
 r.target_year,r.target_month,r.fact_sheet
FROM news_article a JOIN analysis_result r ON r.analysis_id=a.analysis_id
JOIN station s ON s.station_id=r.station_id;
