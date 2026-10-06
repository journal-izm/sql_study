// .env의 DB 접속정보와 외부 API 키를 process.env에서 읽을 수 있게 합니다.
require('dotenv').config();
const express = require('express');
const path = require('path');
const mysql = require('mysql2/promise');

const app = express();
const PORT = process.env.PORT || 8081;

// 브라우저 JSON 본문을 req.body 객체로 읽게 하는 미들웨어입니다.
app.use(express.json());
// public 폴더의 HTML/CSS/JavaScript를 브라우저에 제공합니다.
app.use(express.static(path.join(__dirname, 'public')));

const CITIES = {
  seoul: { query: 'Seoul,KR', name: '서울' },
  busan: { query: 'Busan,KR', name: '부산' },
  jeju: { query: 'Jeju,KR', name: '제주' },
  gwangju: { query: 'Gwangju,KR', name: '광주' }
};

// MySQL 연결 풀: 요청마다 새 연결을 만들기보다 여러 연결을 재사용합니다.
const pool = mysql.createPool({
  host: process.env.DB_HOST || '127.0.0.1',
  port: Number(process.env.DB_PORT || 3306),
  user: process.env.DB_USER || 'root',
  password: process.env.DB_PASSWORD || '',
  database: process.env.DB_NAME || 'weatherNewsDB',
  waitForConnections: true,
  connectionLimit: 10,
  charset: 'utf8mb4'
});

// DB 제약 위반은 서버 장애(500) 대신 입력/충돌 응답으로 구분
// MySQL 제약 위반을 HTTP 409/400으로 구분합니다. FK의 존재 여부는 DB에서 검사합니다.
function dbStatus(error) {
  if ([1062, 1451, 1452].includes(error.errno)) return 409;
  if ([1048, 1406, 3819, 1265, 1366].includes(error.errno)) return 400;
  return 500;
}
// OpenWeather 현재 관측을 호출합니다. AI 기사 작성이나 일평균/예보 조회가 아닙니다.
async function fetchWeather(cityKey) {
  const key = String(cityKey || 'seoul').toLowerCase();
  const city = CITIES[key];
  if (!city) throw new Error('city는 seoul, busan, jeju, gwangju 중 하나여야 합니다.');

  const apiKey = process.env.OPENWEATHER_API_KEY?.trim();
  if (!apiKey) throw new Error('OPENWEATHER_API_KEY를 설정하세요.');

  const url = new URL('https://api.openweathermap.org/data/2.5/weather');
  url.searchParams.set('q', city.query);
  url.searchParams.set('appid', apiKey);
  // metric을 요청해 기온은 섭씨, 풍속은 m/s 기준으로 받습니다.
  url.searchParams.set('units', 'metric');
  url.searchParams.set('lang', 'kr');

  const response = await fetch(url);
  if (!response.ok) throw new Error(`OpenWeather 오류 HTTP ${response.status}`);

  // 외부 응답 JSON을 JavaScript 객체로 변환합니다.
  const data = await response.json();
  return {
    cityCode: key,
    regionName: city.name,
    cityName: data.name,
    temperature: data.main.temp,
    feelsLike: data.main.feels_like,
    humidity: data.main.humidity,
    windSpeed: data.wind.speed,
    description: data.weather?.[0]?.description || '정보 없음',
    observedAt: data.dt ? new Date(data.dt * 1000) : null
  };
}

// GET 연결 점검: SELECT 1이 정상 실행되는지 확인합니다.
app.get('/api/health', async (req, res) => {
  try {
    const [rows] = await pool.query('SELECT 1 AS ok');
    res.json({ success: true, mysql: rows[0].ok === 1 });
  } catch (error) {
    res.status(503).json({ success: false, error: error.message });
  }
});

// GET 날씨 조회: 외부 값을 반환하며 관측 테이블에 저장하지 않습니다.
app.get('/api/weather', async (req, res) => {
  try {
    res.json({ success: true, data: await fetchWeather(req.query.city) });
  } catch (error) {
    res.status(dbStatus(error)).json({ success: false, error: error.message });
  }
});

// POST 수집: 외부 값을 INSERT하고 생성된 weather_id를 반환합니다. 중복은 UNIQUE가 막습니다.
app.post('/api/weather/collect', async (req, res) => {
  try {
    const w = await fetchWeather(req.query.city);
    const [result] = await pool.execute(
      `INSERT INTO weather_observation
      (city_code,region_name,city_name,temperature,feels_like,humidity,wind_speed,description,observed_at)
      VALUES (?,?,?,?,?,?,?,?,?)`,
      [w.cityCode,w.regionName,w.cityName,w.temperature,w.feelsLike,w.humidity,w.windSpeed,w.description,w.observedAt]
    );
    res.status(201).json({ success: true, weatherId: result.insertId, data: w });
  } catch (error) {
    res.status(dbStatus(error)).json({ success: false, error: error.message });
  }
});

// GROUP BY로 지역별 수집값을 집계합니다. 관측 간격이 일정하지 않아 공식 일평균은 아닙니다.
app.get('/api/analysis/summary', async (req, res) => {
  try {
    const [rows] = await pool.query(
      `SELECT region_name,
              COUNT(*) AS observation_count,
              ROUND(AVG(temperature),1) AS avg_temperature,
              MAX(temperature) AS max_temperature,
              MIN(temperature) AS min_temperature,
              ROUND(AVG(humidity),1) AS avg_humidity,
              MAX(wind_speed) AS max_wind_speed
       FROM weather_observation
       GROUP BY region_name
       ORDER BY avg_temperature DESC`
    );
    res.json({ success: true, count: rows.length, data: rows });
  } catch (error) {
    res.status(dbStatus(error)).json({ success: false, error: error.message });
  }
});

// C
// POST 생성: 서버 입력 검사 → SQL INSERT → PK로 재조회 → 201 응답 순서입니다.
app.post('/api/articles', async (req, res) => {
  try {
    // 구조 분해로 req.body에서 필요한 값을 꺼냅니다. 빠진 상태는 DRAFT, 연결 ID는 null입니다.
    const { sourceRegion, title, leadText, bodyText, status='DRAFT', weatherId=null } = req.body;
    // 공백 제목을 검사합니다. DB의 제목 CHECK도 최종 저장 단계에서 적용됩니다.
    if (!title?.trim()) return res.status(400).json({ success:false, error:'title은 필수입니다.' });

    // 정수 형태와 양수 조건을 검사합니다. 해당 ID가 DB에 존재하는지는 FK가 검사합니다.
    if (weatherId !== null && (!Number.isSafeInteger(weatherId) || weatherId <= 0)) return res.status(400).json({success:false,error:'weatherId는 양의 정수 또는 null입니다.'});
    const [result] = await pool.execute(
      `INSERT INTO news_article
      (source_region,title,lead_text,body_text,status,weather_id)
      VALUES (?,?,?,?,?,?)`,
      [sourceRegion || null, title.trim(), leadText || null, bodyText || null, status, weatherId]
    );

    const [rows] = await pool.execute(
      'SELECT * FROM news_article WHERE article_id=?',
      [result.insertId]
    );
    res.status(201).json({ success:true, crud:'CREATE', data:rows[0] });
  } catch (error) {
    res.status(dbStatus(error)).json({ success:false, error:error.message });
  }
});

// R ALL
// GET 목록: 전체 기사를 최신 ID 순으로 조회합니다.
app.get('/api/articles', async (req, res) => {
  try {
    const [rows] = await pool.query(
      'SELECT * FROM news_article ORDER BY article_id DESC'
    );
    res.json({ success:true, crud:'READ', count:rows.length, data:rows });
  } catch (error) {
    res.status(dbStatus(error)).json({ success:false, error:error.message });
  }
});

// R ONE
// GET 단건: URL의 :id 값을 req.params.id로 받아 조회합니다. 없으면 404입니다.
app.get('/api/articles/:id', async (req, res) => {
  try {
    const [rows] = await pool.execute(
      'SELECT * FROM news_article WHERE article_id=?',
      [Number(req.params.id)]
    );
    if (!rows.length) return res.status(404).json({ success:false, error:'기사를 찾을 수 없습니다.' });
    res.json({ success:true, crud:'READ', data:rows[0] });
  } catch (error) {
    res.status(dbStatus(error)).json({ success:false, error:error.message });
  }
});

// PUT: 모든 수정 가능 필드를 전달하여 전체 교체합니다. null도 명시합니다.
// article_id와 생성 시각은 서버 관리 값이므로 교체하지 않습니다.
// PUT 전체 교체: 6개 수정 필드 모두 필수입니다. PK와 생성 시각은 교체하지 않습니다.
app.put('/api/articles/:id', async (req, res) => {
  try {
    const id = Number(req.params.id);
    if (!Number.isSafeInteger(id) || id <= 0) return res.status(400).json({success:false,error:'id는 양의 정수입니다.'});
    const keys = ['sourceRegion','title','leadText','bodyText','status','weatherId'];
    if (!keys.every(k => Object.hasOwn(req.body, k))) return res.status(400).json({success:false,error:'PUT은 sourceRegion, title, leadText, bodyText, status, weatherId를 모두 전달하세요. 비어 있는 선택 항목은 null입니다.'});
    const {sourceRegion,title,leadText,bodyText,status,weatherId} = req.body;
    if (typeof title !== 'string' || !title.trim() || title.length > 200) return res.status(400).json({success:false,error:'title은 1~200자이며 공백만 입력할 수 없습니다.'});
    if (!['DRAFT','REVIEW','APPROVED','REJECTED'].includes(status)) return res.status(400).json({success:false,error:'status 값을 확인하세요.'});
    if ([sourceRegion,leadText,bodyText].some(v => v !== null && typeof v !== 'string') || (sourceRegion !== null && sourceRegion.length > 30)) return res.status(400).json({success:false,error:'선택 문자열의 형식/지역 길이를 확인하세요.'});
    // 정수 형태와 양수 조건을 검사합니다. 해당 ID가 DB에 존재하는지는 FK가 검사합니다.
    if (weatherId !== null && (!Number.isSafeInteger(weatherId) || weatherId <= 0)) return res.status(400).json({success:false,error:'weatherId는 양의 정수 또는 null입니다.'});
    // 동일 내용으로 PUT을 반복해도 404가 되지 않도록 존재 여부는 SELECT로 확인합니다.
    const [found] = await pool.execute('SELECT article_id FROM news_article WHERE article_id=?', [id]);
    if (!found.length) return res.status(404).json({success:false,error:'기사를 찾을 수 없습니다.'});
    await pool.execute('UPDATE news_article SET source_region=?,title=?,lead_text=?,body_text=?,status=?,weather_id=? WHERE article_id=?', [sourceRegion,title,leadText,bodyText,status,weatherId,id]);
    const [rows] = await pool.execute('SELECT * FROM news_article WHERE article_id=?', [id]);
    if (!rows.length) return res.status(404).json({success:false,error:'기사를 찾을 수 없습니다.'});
    res.json({success:true,crud:'UPDATE',method:'PUT',data:rows[0]});
  } catch (error) {
    res.status(dbStatus(error)).json({success:false,error:error.message});
  }
});

// PATCH: 요청에 들어온 필드만 변경합니다.
// PATCH 부분 수정: 보낸 필드만 UPDATE에 포함합니다. 생략과 null은 서로 다릅니다.
app.patch('/api/articles/:id', async (req, res) => {
  try {
    const id = Number(req.params.id);
    if (req.body.weatherId !== undefined && req.body.weatherId !== null && (!Number.isSafeInteger(req.body.weatherId) || req.body.weatherId <= 0)) return res.status(400).json({success:false,error:'weatherId는 양의 정수 또는 null입니다.'});
    // 입력 필드와 실제 DB 열 이름을 연결하는 허용 목록입니다. 임의 열 이름을 요청에서 받지 않습니다.
    const map = {
      sourceRegion:'source_region',
      title:'title',
      leadText:'lead_text',
      bodyText:'body_text',
      status:'status',
      weatherId:'weather_id'
    };

    const setParts = [];
    const values = [];
    for (const [input, col] of Object.entries(map)) {
      if (req.body[input] !== undefined) {
        // 수정할 열 목록을 만듭니다. 값은 ? 바인딩으로 분리해 SQL 코드로 해석되지 않게 합니다.
        setParts.push(`${col}=?`);
        values.push(req.body[input]);
      }
    }

    if (!setParts.length) {
      return res.status(400).json({ success:false, error:'수정할 값을 입력하세요.' });
    }

    // WHERE의 article_id 자리도 ?이므로 ID를 값 배열의 마지막에 넣습니다.
    values.push(id);
    const [result] = await pool.execute(
      `UPDATE news_article SET ${setParts.join(', ')} WHERE article_id=?`,
      values
    );

    const [rows] = await pool.execute(
      'SELECT * FROM news_article WHERE article_id=?',
      [id]
    );
    if (!rows.length) return res.status(404).json({success:false,error:'기사를 찾을 수 없습니다.'});
    res.json({ success:true, crud:'UPDATE', method:'PATCH', data:rows[0] });
  } catch (error) {
    res.status(dbStatus(error)).json({ success:false, error:error.message });
  }
});

// D
// DELETE 기사: 삭제 전 조회해 반환할 값을 보관합니다. 부모 관측은 유지됩니다.
app.delete('/api/articles/:id', async (req, res) => {
  try {
    const id = Number(req.params.id);
    const [rows] = await pool.execute(
      'SELECT * FROM news_article WHERE article_id=?',
      [id]
    );
    if (!rows.length) return res.status(404).json({ success:false, error:'기사를 찾을 수 없습니다.' });

    await pool.execute(
      'DELETE FROM news_article WHERE article_id=?',
      [id]
    );

    res.json({ success:true, crud:'DELETE', deleted:rows[0] });
  } catch (error) {
    res.status(dbStatus(error)).json({ success:false, error:error.message });
  }
});

// 설정 포트에서 서버를 시작합니다. 브라우저는 출력된 localhost 주소에 접속합니다.
app.listen(PORT, () => {
  console.log(`OpenWeather + Node.js + MySQL CRUD`);
  console.log(`http://localhost:${PORT}`);
});

