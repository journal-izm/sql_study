import test from 'node:test';
import assert from 'node:assert/strict';
import iconv from 'iconv-lite';
import { parseCSV, summarize } from '../weather-lab.js';
const header = '지점,지점명,일시,평균기온(℃)\n';
test('CP949 원본에서 0과 NULL 구분', () => {
 const rows = parseCSV(iconv.encode(header + '108,서울,2025-09-01,0\n108,서울,2025-09-02,\n', 'cp949'));
 assert.equal(rows[0].avg_temp_c, 0); assert.equal(rows[1].avg_temp_c, null);
});
test('중복 날짜 거부', () => assert.throws(() => parseCSV(Buffer.from(header+'108,서울,2025-09-01,20\n108,서울,2025-09-01,20\n')), /중복/));
test('비정상 숫자/결측부호 거부', () => {
 for (const value of ['NaN','-999','20.123']) assert.throws(() => parseCSV(Buffer.from(header+`108,서울,2025-09-01,${value}\n`)));
});
test('시간자료와 잘못된 날짜 거부', () => {
 for (const day of ['2025-09-01 01:00','2025-02-30']) assert.throws(() => parseCSV(Buffer.from(header+`108,서울,${day},20\n`)));
});
test('필수 열 누락 거부', () => assert.throws(() => parseCSV(Buffer.from('지점,일시\n108,2025-09-01\n')), /필수 열/));
test('완전한 월 평균 계산', () => {
 const rows=Array.from({length:30},(_,i)=>({observed_date:`2025-09-${String(i+1).padStart(2,'0')}`,avg_temp_c:i+1}));
 assert.equal(summarize(rows,2025,9).mean_daily_temperature_c,15.5);
});
test('날짜 누락/NULL 시 분석 중단', () => {
 const rows=Array.from({length:29},(_,i)=>({observed_date:`2025-09-${String(i+1).padStart(2,'0')}`,avg_temp_c:i===0?null:20}));
 assert.throws(()=>summarize(rows,2025,9),/누락 날짜/);
});
