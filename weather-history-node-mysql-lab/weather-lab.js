// 실제 CSV → 검증 → MySQL → 같은 달 비교 → 사람이 쓴 기사 저장.
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { parseArgs } from 'node:util';
import { TextDecoder } from 'node:util';
import { parse } from 'csv-parse/sync';
import iconv from 'iconv-lite';
import mysql from 'mysql2/promise';
import dotenv from 'dotenv';

const root = path.dirname(fileURLToPath(import.meta.url));
const sourceURL = 'https://data.kma.go.kr/data/grnd/selectAsosRltmList.do?pgmNo=36';
dotenv.config({ path: path.join(root, '.env'), quiet: true });
const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
const norm = s => s.replace(/^\uFEFF/, '').replace(/\s/g, '').replace('°C', '℃');
export function daysInMonth(year, month) {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}
function checkDate(s) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) throw Error('일자료 날짜는 YYYY-MM-DD여야 합니다.');
  const [y, m, d] = s.split('-').map(Number);
  if (y < 1904 || m < 1 || m > 12 || d < 1 || d > daysInMonth(y, m) || s > today()) throw Error('유효한 과거 관측 날짜가 아닙니다.');
}
export function parseCSV(buffer, encoding) {
  let text;
  if (encoding) {
    if (!iconv.encodingExists(encoding)) throw Error('지원하지 않는 인코딩입니다.');
    text = iconv.decode(buffer, encoding);
  } else {
    try { text = new TextDecoder('utf-8', { fatal: true }).decode(buffer); }
    catch { text = iconv.decode(buffer, 'cp949'); }
  }
  const records = parse(text, { bom: true, columns: true, skip_empty_lines: true, trim: true });
  if (!records.length) throw Error('관측 행이 없습니다.');
  const headers = new Map(Object.keys(records[0]).map(k => [norm(k), k]));
  const col = (...names) => {
    for (const n of names) if (headers.has(n)) return headers.get(n);
    throw Error(`필수 열 없음: ${names.join('/')} / 실제 열: ${[...headers.values()].join(', ')}`);
  };
  const sidCol = col('지점', 'station_id'), nameCol = col('지점명', 'station_name');
  const dateCol = col('일시', 'observed_date'), tempCol = col('평균기온(℃)', 'avg_temp_c');
  const seen = new Set(), stations = new Map();
  return records.map((r, i) => {
    try {
      const sid = Number(r[sidCol]), name = r[nameCol], day = r[dateCol];
      if (!/^\d+$/.test(r[sidCol]) || !Number.isSafeInteger(sid) || sid <= 0 || !name || name.length > 100) throw Error('관측소 코드/이름 오류');
      checkDate(day);
      const value = r[tempCol];
      let temp = null;
      // NULL과 0℃를 구분합니다. 알려지지 않은 결측 부호는 오류로 중단합니다.
      if (!['', 'NA', 'N/A', 'null', 'NULL', '-'].includes(value)) {
        if (!/^[+-]?\d+(\.\d{1,2})?$/.test(value)) throw Error('기온은 소수 2자리 이내 숫자여야 합니다.');
        temp = Number(value);
        if (!Number.isFinite(temp) || temp < -100 || temp > 100) throw Error('기온/단위/결측 부호 확인 필요');
      }
      const key = `${sid}/${day}`;
      if (seen.has(key)) throw Error('같은 관측소/날짜가 파일 안에서 중복됩니다.');
      if (stations.has(sid) && stations.get(sid) !== name) throw Error('동일 관측소의 이름 불일치');
      seen.add(key); stations.set(sid, name);
      return { station_id: sid, station_name: name, observed_date: day, avg_temp_c: temp };
    } catch (e) { throw Error(`CSV 데이터 ${i + 1}번째 행: ${e.message}`); }
  });
}
async function connect() {
  return mysql.createConnection({ host: process.env.MYSQL_HOST || '127.0.0.1', port: Number(process.env.MYSQL_PORT || 3306),
    user: process.env.MYSQL_USER || 'root', password: process.env.MYSQL_PASSWORD || '',
    database: process.env.MYSQL_DATABASE || 'weather_history_lab', charset: 'utf8mb4', dateStrings: true });
}
async function importCSV(file, options) {
  const bytes = await fs.readFile(file), rows = parseCSV(bytes, options.encoding);
  console.log(`검증 완료: ${rows.length}행 / 결측 기온 ${rows.filter(r => r.avg_temp_c === null).length}건`);
  if (options['validate-only']) return;
  const hash = createHash('sha256').update(bytes).digest('hex');
  const db = await connect();
  try {
    await db.beginTransaction();
    const [batches] = await db.execute('SELECT batch_id FROM import_batch WHERE sha256=?', [hash]);
    if (batches.length) { await db.rollback(); console.log('이미 저장된 동일 파일입니다.'); return; }
    const [batch] = await db.execute('INSERT INTO import_batch(file_name,sha256,source_url) VALUES(?,?,?)', [path.basename(file), hash, options['source-url'] || sourceURL]);
    let inserted = 0, skipped = 0;
    for (const r of rows) {
      const [stations] = await db.execute('SELECT station_name FROM station WHERE station_id=?', [r.station_id]);
      if (stations.length && stations[0].station_name !== r.station_name) throw Error('DB와 CSV의 관측소 이름이 다릅니다.');
      if (!stations.length) await db.execute('INSERT INTO station VALUES(?,?)', [r.station_id, r.station_name]);
      const [existing] = await db.execute('SELECT avg_temp_c FROM daily_weather WHERE station_id=? AND observed_date=?', [r.station_id, r.observed_date]);
      if (existing.length) {
        const old = existing[0].avg_temp_c === null ? null : Number(existing[0].avg_temp_c);
        if (old !== r.avg_temp_c) throw Error(`${r.observed_date}: 기존 기온과 다릅니다. 정정 여부 확인 필요. 자동 덮어쓰기는 하지 않습니다.`);
        skipped++; continue;
      }
      await db.execute('INSERT INTO daily_weather(station_id,observed_date,avg_temp_c,batch_id) VALUES(?,?,?,?)', [r.station_id, r.observed_date, r.avg_temp_c, batch.insertId]);
      inserted++;
    }
    await db.commit(); console.log(`저장 ${inserted}행 / 동일 값 생략 ${skipped}행 / batch_id=${batch.insertId}`);
  } catch (e) { await db.rollback(); throw e; } finally { await db.end(); }
}
export function summarize(rows, year, month) {
  const count = daysInMonth(year, month), prefix = `${year}-${String(month).padStart(2, '0')}-`;
  const validDates = new Set(), missing = [], nullDays = [];
  let sum = 0;
  for (const r of rows) {
    checkDate(r.observed_date);
    if (!r.observed_date.startsWith(prefix) || validDates.has(r.observed_date)) throw Error('분석 기간/중복 날짜 오류');
    validDates.add(r.observed_date);
    if (r.avg_temp_c === null) { nullDays.push(r.observed_date); continue; }
    const temp = Number(r.avg_temp_c);
    if (!Number.isFinite(temp)) throw Error('기온 숫자 오류');
    // 일별 소수 2자리 값을 정수로 합산해 불필요한 부동소수점 누적 오차를 줄입니다.
    sum += Math.round(temp * 100);
  }
  for (let d = 1; d <= count; d++) {
    const s = prefix + String(d).padStart(2, '0');
    if (!validDates.has(s)) missing.push(s);
  }
  if (missing.length || nullDays.length) throw Error(`${year}-${month}: 누락 날짜 ${missing.join(',')} / 결측 기온 ${nullDays.join(',')}`);
  return { year, month, expected_days: count, valid_days: count, mean_daily_temperature_c: rounded(sum / count / 100), rawMean: sum / count / 100 };
}
function rounded(n) { return Math.sign(n) * Math.round((Math.abs(n) + Number.EPSILON) * 100) / 100; }
function positiveInt(value, label, min, max) {
  if (!value || !/^\d+$/.test(value)) throw Error(`${label}: 정수가 필요합니다.`);
  const n = Number(value);
  if (!Number.isSafeInteger(n) || n < min || n > max) throw Error(`${label}: 허용 범위 ${min}~${max}`);
  return n;
}
async function compare(options) {
  const sid = positiveInt(options.station, 'station', 1, 2147483647);
  const baseYear = positiveInt(options['baseline-year'], 'baseline-year', 1904, 9999);
  const targetYear = positiveInt(options['target-year'], 'target-year', 1904, 9999);
  const month = positiveInt(options.month, 'month', 1, 12);
  if (baseYear === targetYear) throw Error('서로 다른 두 해가 필요합니다.');
  const ending = y => `${y}-${String(month).padStart(2,'0')}-${daysInMonth(y, month)}`;
  if (ending(baseYear) >= today() || ending(targetYear) >= today()) throw Error('관측이 완료된 달을 선택하세요.');
  const db = await connect();
  let facts;
  try {
    // 두 기간을 같은 DB 스냅샷에서 읽고 분석을 저장합니다.
    await db.beginTransaction();
    const [stations] = await db.execute('SELECT station_name FROM station WHERE station_id=?', [sid]);
    if (!stations.length) throw Error('관측소가 없습니다. 먼저 CSV를 가져오세요.');
    const summaries = [], sources = new Map();
    for (const y of [baseYear, targetYear]) {
      const start = `${y}-${String(month).padStart(2,'0')}-01`;
      const [rows] = await db.execute('SELECT w.observed_date,w.avg_temp_c,b.batch_id,b.file_name,b.sha256,b.source_url FROM daily_weather w JOIN import_batch b ON b.batch_id=w.batch_id WHERE w.station_id=? AND w.observed_date BETWEEN ? AND ? ORDER BY w.observed_date', [sid, start, ending(y)]);
      summaries.push(summarize(rows, y, month));
      for (const r of rows) sources.set(r.batch_id, { batch_id: r.batch_id, file_name: r.file_name, sha256: r.sha256, source_url: r.source_url });
    }
    const difference = rounded(summaries[1].rawMean - summaries[0].rawMean);
    for (const s of summaries) delete s.rawMean;
    facts = { station_id: sid, station_name: stations[0].station_name, metric: '일평균기온의 월 산술평균', unit: '℃', baseline: summaries[0], target: summaries[1], difference_c: difference,
      sources: [...sources.values()], limitations: ['두 기간 비교로 장기 기후변화나 변화 원인을 단정하지 않음', '공식 월 통계와 산출/반올림 방식에 따라 차이가 있을 수 있음'] };
    const [result] = await db.execute('INSERT INTO analysis_result(station_id,baseline_year,target_year,target_month,fact_sheet) VALUES(?,?,?,?,?)', [sid, baseYear, targetYear, month, JSON.stringify(facts)]);
    facts.analysis_id = result.insertId;
    await db.commit();
  } catch (e) { await db.rollback(); throw e; } finally { await db.end(); }
  const output = options.output || 'data/results/fact_sheet.json';
  await fs.mkdir(path.dirname(output), { recursive: true });
  await fs.writeFile(output, JSON.stringify(facts, null, 2), 'utf8');
  console.log(JSON.stringify(facts, null, 2)); console.log(`근거 저장: ${output}`);
}
async function saveArticle(options) {
  const id = positiveInt(options['analysis-id'], 'analysis-id', 1, Number.MAX_SAFE_INTEGER);
  if (!options.title?.trim() || options.title.trim().length > 200 || !options.body) throw Error('제목 1~200자, 본문 파일이 필요합니다.');
  const body = (await fs.readFile(options.body, 'utf8')).replace(/^\uFEFF/, '').trim();
  if (!body) throw Error('본문이 비어 있습니다.');
  const db = await connect();
  try {
    await db.beginTransaction();
    const [r] = await db.execute('INSERT INTO news_article(analysis_id,title,lead_text,body_text,author_type) VALUES(?,?,?,?,?)', [id, options.title.trim(), options.lead || null, body, 'HUMAN']);
    await db.commit(); console.log(`기사 저장: article_id=${r.insertId} / DRAFT`);
  } catch (e) { await db.rollback(); throw e; } finally { await db.end(); }
}
async function main() {
  const { values, positionals } = parseArgs({ allowPositionals: true, options: {
    encoding: { type: 'string' }, 'source-url': { type: 'string' }, 'validate-only': { type: 'boolean' },
    station: { type: 'string' }, 'baseline-year': { type: 'string' }, 'target-year': { type: 'string' }, month: { type: 'string' }, output: { type: 'string' },
    'analysis-id': { type: 'string' }, title: { type: 'string' }, lead: { type: 'string' }, body: { type: 'string' }, help: { type: 'boolean' }
  } });
  if (values.help || !positionals.length) { console.log('node weather-lab.js import-csv 파일.csv [--validate-only]\nnode weather-lab.js compare --station 108 --baseline-year 2025 --target-year 2026 --month 9\nnode weather-lab.js save-article --analysis-id 1 --title "제목" --body 본문.txt'); return; }
  if (positionals[0] === 'import-csv' && positionals[1]) await importCSV(positionals[1], values);
  else if (positionals[0] === 'compare') await compare(values);
  else if (positionals[0] === 'save-article') await saveArticle(values);
  else throw Error('명령/파일 경로를 확인하세요. --help로 사용법을 확인합니다.');
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(e => { console.error(`실행 실패: ${e.message}`); process.exitCode = 1; });
}
