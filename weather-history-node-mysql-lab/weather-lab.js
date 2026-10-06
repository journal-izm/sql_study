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
// 윤년을 포함한 해당 월의 일수를 구합니다. 월말 누락 검사의 기준입니다.
export function daysInMonth(year, month) {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}
// YYYY-MM-DD 형식과 실제 달력 날짜, 미래 관측 여부를 검사합니다.
function checkDate(s) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) throw Error('일자료 날짜는 YYYY-MM-DD여야 합니다.');
  const [y, m, d] = s.split('-').map(Number);
  if (y < 1904 || m < 1 || m > 12 || d < 1 || d > daysInMonth(y, m) || s > today()) throw Error('유효한 과거 관측 날짜가 아닙니다.');
}
// UTF-8/CP949 CSV를 객체 배열로 변환하고 필수 열·기온·중복을 검사합니다. 여기서는 DB를 쓰지 않습니다.
export function parseCSV(buffer, encoding) {
  let text;
  if (encoding) {
    if (!iconv.encodingExists(encoding)) throw Error('지원하지 않는 인코딩입니다.');
    text = iconv.decode(buffer, encoding);
  } else {
    try { text = new TextDecoder('utf-8', { fatal: true }).decode(buffer); }
    catch { text = iconv.decode(buffer, 'cp949'); }
  }
  // columns:true는 첫 줄을 객체의 키로 사용합니다. 각 행의 값을 열 이름으로 찾습니다.
  const records = parse(text, { bom: true, columns: true, skip_empty_lines: true, trim: true });
  if (!records.length) throw Error('관측 행이 없습니다.');
  // 표준화한 열 이름 → 실제 CSV 열 이름을 Map에 저장합니다.
  const headers = new Map(Object.keys(records[0]).map(k => [norm(k), k]));
  const col = (...names) => {
    for (const n of names) if (headers.has(n)) return headers.get(n);
    throw Error(`필수 열 없음: ${names.join('/')} / 실제 열: ${[...headers.values()].join(', ')}`);
  };
  const sidCol = col('지점', 'station_id'), nameCol = col('지점명', 'station_name');
  const dateCol = col('일시', 'observed_date'), tempCol = col('평균기온(℃)', 'avg_temp_c');
  // Set은 날짜 중복을, Map은 같은 지점 코드의 이름 일관성을 확인합니다.
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
// MySQL 연결을 생성합니다. dateStrings는 DATE를 날짜 문자열로 반환해 시간대 변환을 피합니다.
async function connect() {
  return mysql.createConnection({ host: process.env.MYSQL_HOST || '127.0.0.1', port: Number(process.env.MYSQL_PORT || 3306),
    user: process.env.MYSQL_USER || 'root', password: process.env.MYSQL_PASSWORD || '',
    database: process.env.MYSQL_DATABASE || 'weather_history_lab', charset: 'utf8mb4', dateStrings: true });
}
// 한 CSV를 한 트랜잭션으로 가져옵니다. 재수집과 동일 관측 날짜 중복을 각각 확인합니다.
async function importCSV(file, options) {
  const bytes = await fs.readFile(file), rows = parseCSV(bytes, options.encoding);
  console.log(`검증 완료: ${rows.length}행 / 결측 기온 ${rows.filter(r => r.avg_temp_c === null).length}건`);
  if (options['validate-only']) return;
  // 파일 전체의 SHA256으로 파일명이 바뀌어도 동일한 원본인지 확인합니다.
  const hash = createHash('sha256').update(bytes).digest('hex');
  const db = await connect();
  try {
    // 지금부터 쓰기 작업을 묶습니다. 실패하면 rollback하고 성공하면 commit합니다.
    await db.beginTransaction();
    const [batches] = await db.execute('SELECT batch_id FROM import_batch WHERE sha256=?', [hash]);
    if (batches.length) { await db.rollback(); console.log('이미 저장된 동일 파일입니다.'); return; }
    // 원본 메타정보의 PK를 얻어 관측 행마다 출처를 연결합니다.
    const [batch] = await db.execute('INSERT INTO import_batch(file_name,sha256,source_url) VALUES(?,?,?)', [path.basename(file), hash, options['source-url'] || sourceURL]);
    let inserted = 0, skipped = 0;
    for (const r of rows) {
      const [stations] = await db.execute('SELECT station_name FROM station WHERE station_id=?', [r.station_id]);
      if (stations.length && stations[0].station_name !== r.station_name) throw Error('DB와 CSV의 관측소 이름이 다릅니다.');
      if (!stations.length) await db.execute('INSERT INTO station VALUES(?,?)', [r.station_id, r.station_name]);
      // DB UNIQUE에 더해 저장된 관측값과 입력 값을 비교해 정정 자료를 자동 덮어쓰지 않습니다.
      const [existing] = await db.execute('SELECT avg_temp_c FROM daily_weather WHERE station_id=? AND observed_date=?', [r.station_id, r.observed_date]);
      if (existing.length) {
        // MySQL DECIMAL이 문자열로 반환될 수 있어 숫자로 비교합니다. NULL은 그대로 유지합니다.
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
// 모든 날짜의 값이 갖춰진 달만 평균을 계산합니다. 부분 자료를 완전한 월평균으로 표현하지 않습니다.
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
// 표시할 때만 소수 둘째 자리로 반올림합니다. 평균 차이는 반올림 전 값으로 계산합니다.
function rounded(n) { return Math.sign(n) * Math.round((Math.abs(n) + Number.EPSILON) * 100) / 100; }
// 명령줄 문자열을 정수로 변환하고 범위를 검사합니다. 날짜/관측소 ID 입력 실수를 막습니다.
function positiveInt(value, label, min, max) {
  if (!value || !/^\d+$/.test(value)) throw Error(`${label}: 정수가 필요합니다.`);
  const n = Number(value);
  if (!Number.isSafeInteger(n) || n < min || n > max) throw Error(`${label}: 허용 범위 ${min}~${max}`);
  return n;
}
// 두 해의 같은 달을 비교한 뒤 분석 근거를 DB와 fact_sheet.json에 저장합니다.
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
    // 지금부터 쓰기 작업을 묶습니다. 실패하면 rollback하고 성공하면 commit합니다.
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
    // 대상 해 평균 - 기준 해 평균. 양수면 높음, 음수면 낮음입니다.
    const difference = rounded(summaries[1].rawMean - summaries[0].rawMean);
    for (const s of summaries) delete s.rawMean;
    // 기사 근거: 수치뿐 아니라 지역/기간/단위/원본 파일 해시/출처와 해석 한계를 포함합니다.
    facts = { station_id: sid, station_name: stations[0].station_name, metric: '일평균기온의 월 산술평균', unit: '℃', baseline: summaries[0], target: summaries[1], difference_c: difference,
      sources: [...sources.values()], limitations: ['두 기간 비교로 장기 기후변화나 변화 원인을 단정하지 않음', '공식 월 통계와 산출/반올림 방식에 따라 차이가 있을 수 있음'] };
    const [result] = await db.execute('INSERT INTO analysis_result(station_id,baseline_year,target_year,target_month,fact_sheet) VALUES(?,?,?,?,?)', [sid, baseYear, targetYear, month, JSON.stringify(facts)]);
    facts.analysis_id = result.insertId;
    await db.commit();
  } catch (e) { await db.rollback(); throw e; } finally { await db.end(); }
  const output = options.output || 'data/results/fact_sheet.json';
  await fs.mkdir(path.dirname(output), { recursive: true });
  // UTF-8 JSON으로 근거를 저장해 사람이 확인하거나 이후 AI 입력으로 사용할 수 있게 합니다.
  await fs.writeFile(output, JSON.stringify(facts, null, 2), 'utf8');
  console.log(JSON.stringify(facts, null, 2)); console.log(`근거 저장: ${output}`);
}
// 사람이 작성한 UTF-8 본문을 분석 ID에 연결해 HUMAN/DRAFT로 저장합니다.
async function saveArticle(options) {
  const id = positiveInt(options['analysis-id'], 'analysis-id', 1, Number.MAX_SAFE_INTEGER);
  if (!options.title?.trim() || options.title.trim().length > 200 || !options.body) throw Error('제목 1~200자, 본문 파일이 필요합니다.');
  const body = (await fs.readFile(options.body, 'utf8')).replace(/^\uFEFF/, '').trim();
  if (!body) throw Error('본문이 비어 있습니다.');
  const db = await connect();
  try {
    // 지금부터 쓰기 작업을 묶습니다. 실패하면 rollback하고 성공하면 commit합니다.
    await db.beginTransaction();
    const [r] = await db.execute('INSERT INTO news_article(analysis_id,title,lead_text,body_text,author_type) VALUES(?,?,?,?,?)', [id, options.title.trim(), options.lead || null, body, 'HUMAN']);
    await db.commit(); console.log(`기사 저장: article_id=${r.insertId} / DRAFT`);
  } catch (e) { await db.rollback(); throw e; } finally { await db.end(); }
}
// 명령줄 옵션을 파싱하고 사용자가 선택한 기능으로 분기합니다.
async function main() {
  // parseArgs는 --옵션 값과 명령/파일 경로를 분리합니다.
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
  // 오류를 표시하고 종료 코드 1을 반환합니다. 자동 실행에서도 실패를 감지할 수 있습니다.
  main().catch(e => { console.error(`실행 실패: ${e.message}`); process.exitCode = 1; });
}
