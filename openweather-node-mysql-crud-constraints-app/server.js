require('dotenv').config();
const express = require('express');
const path = require('path');
const mysql = require('mysql2/promise');

const app = express();
const PORT = process.env.PORT || 8081;

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

const CITIES = {
  seoul: { query: 'Seoul,KR', name: '서울' },
  busan: { query: 'Busan,KR', name: '부산' },
  jeju: { query: 'Jeju,KR', name: '제주' },
  gwangju: { query: 'Gwangju,KR', name: '광주' }
};

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
function dbStatus(error) {
  if ([1062, 1451, 1452].includes(error.errno)) return 409;
  if ([1048, 1406, 3819, 1265, 1366].includes(error.errno)) return 400;
  return 500;
}
async function fetchWeather(cityKey) {
  const key = String(cityKey || 'seoul').toLowerCase();
  const city = CITIES[key];
  if (!city) throw new Error('city는 seoul, busan, jeju, gwangju 중 하나여야 합니다.');

  const apiKey = process.env.OPENWEATHER_API_KEY?.trim();
  if (!apiKey) throw new Error('OPENWEATHER_API_KEY를 설정하세요.');

  const url = new URL('https://api.openweathermap.org/data/2.5/weather');
  url.searchParams.set('q', city.query);
  url.searchParams.set('appid', apiKey);
  url.searchParams.set('units', 'metric');
  url.searchParams.set('lang', 'kr');

  const response = await fetch(url);
  if (!response.ok) throw new Error(`OpenWeather 오류 HTTP ${response.status}`);

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

app.get('/api/health', async (req, res) => {
  try {
    const [rows] = await pool.query('SELECT 1 AS ok');
    res.json({ success: true, mysql: rows[0].ok === 1 });
  } catch (error) {
    res.status(503).json({ success: false, error: error.message });
  }
});

app.get('/api/weather', async (req, res) => {
  try {
    res.json({ success: true, data: await fetchWeather(req.query.city) });
  } catch (error) {
    res.status(dbStatus(error)).json({ success: false, error: error.message });
  }
});

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
app.post('/api/articles', async (req, res) => {
  try {
    const { sourceRegion, title, leadText, bodyText, status='DRAFT', weatherId=null } = req.body;
    if (!title?.trim()) return res.status(400).json({ success:false, error:'title은 필수입니다.' });

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

// U
app.patch('/api/articles/:id', async (req, res) => {
  try {
    const id = Number(req.params.id);
    if (req.body.weatherId !== undefined && req.body.weatherId !== null && (!Number.isSafeInteger(req.body.weatherId) || req.body.weatherId <= 0)) return res.status(400).json({success:false,error:'weatherId는 양의 정수 또는 null입니다.'});
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
        setParts.push(`${col}=?`);
        values.push(req.body[input]);
      }
    }

    if (!setParts.length) {
      return res.status(400).json({ success:false, error:'수정할 값을 입력하세요.' });
    }

    values.push(id);
    const [result] = await pool.execute(
      `UPDATE news_article SET ${setParts.join(', ')} WHERE article_id=?`,
      values
    );

    if (!result.affectedRows) return res.status(404).json({ success:false, error:'기사를 찾을 수 없습니다.' });

    const [rows] = await pool.execute(
      'SELECT * FROM news_article WHERE article_id=?',
      [id]
    );
    res.json({ success:true, crud:'UPDATE', data:rows[0] });
  } catch (error) {
    res.status(dbStatus(error)).json({ success:false, error:error.message });
  }
});

// D
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

app.listen(PORT, () => {
  console.log(`OpenWeather + Node.js + MySQL CRUD`);
  console.log(`http://localhost:${PORT}`);
});
