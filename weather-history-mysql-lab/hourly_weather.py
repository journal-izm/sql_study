"""ASOS 시간 CSV 전용 집계. 일자료 테이블에는 쓰지 않습니다."""
import calendar
import csv
import hashlib
import io
import re
from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path


def read_hourly_csv(path, encoding=None):
    raw = Path(path).read_bytes()
    for enc in ([encoding] if encoding else ['utf-8-sig', 'cp949']):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError('시간 CSV 인코딩을 확인하세요. --encoding을 지정할 수 있습니다.')
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError('CSV 헤더가 없습니다.')
    normalized = [re.sub(r'\s+', '', x.lstrip('\ufeff')).replace('°C', '℃') for x in reader.fieldnames]
    if len(set(normalized)) != len(normalized):
        raise ValueError('중복된 CSV 열 이름이 있습니다.')
    headers = dict(zip(normalized, reader.fieldnames))
    def col(*names):
        for name in names:
            if name in headers:
                return headers[name]
        raise ValueError(f'시간 CSV 필수 열 {names}이 없습니다. 일자료는 import-csv를 사용하세요.')
    sid_col, name_col = col('지점', 'station_id'), col('지점명', 'station_name')
    time_col, temp_col = col('일시', 'observed_at'), col('기온(℃)', 'temperature_c')
    qc_col = headers.get('기온QC플래그')
    rows, seen, names = [], set(), {}
    for line, row in enumerate(reader, 2):
        if not any(row.values()):
            continue
        try:
            if None in row or any(v is None for v in row.values()):
                raise ValueError('CSV 열 개수가 헤더와 다릅니다.')
            sid, name = int(row[sid_col]), row[name_col].strip()
            if sid <= 0 or not name or len(name) > 100:
                raise ValueError('관측소 코드/이름을 확인하세요.')
            stamp = row[time_col].strip()
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}[ T]\d{2}:00(?::00)?', stamp):
                raise ValueError('시간 자료는 날짜와 정시 시각(YYYY-MM-DD HH:00)이 필요합니다.')
            moment = datetime.fromisoformat(stamp)
            key = (sid, moment)
            if key in seen:
                raise ValueError('같은 관측소/시각이 중복됩니다.')
            if sid in names and names[sid] != name:
                raise ValueError('같은 지점 코드의 이름이 다릅니다.')
            seen.add(key)
            names[sid] = name
            value = row[temp_col].strip()
            temp = None if value in ('', 'NA', 'N/A', 'null', 'NULL', '-') else Decimal(value)
            if temp is not None and (not temp.is_finite() or not -100 <= temp <= 100):
                raise ValueError('기온 범위/결측 코드를 확인하세요.')
            if temp is not None and temp != temp.quantize(Decimal('0.01')):
                raise ValueError('소수 2자리 초과 기온입니다.')
            rows.append({'station_id': sid, 'station_name': name, 'observed_at': moment,
                         'temperature_c': temp, 'quality_flag': row[qc_col].strip() if qc_col else ''})
        except (ValueError, InvalidOperation, TypeError) as exc:
            raise ValueError(f'시간 CSV {line}행 오류: {exc}') from exc
    if not rows:
        raise ValueError('시간 관측 행이 없습니다.')
    return rows, hashlib.sha256(raw).hexdigest(), enc


def summarize_hourly(rows, *, source_url, file_name, sha256, station=None, timezone='Asia/Seoul'):
    """00:00~23:00 정시 24개가 모두 유효한 날짜만 사용합니다.

    CSV 자체에는 UTC offset이 없으므로 Asia/Seoul은 ASOS 현지시각 해석입니다.
    비어 있지 않은 QC 플래그는 의미를 추측하지 않고 검토 필요로 제외합니다.
    """
    if timezone != 'Asia/Seoul':
        raise ValueError('이 ASOS 실습은 Asia/Seoul 현지 날짜만 지원합니다.')
    if not re.match(r'^https?://', source_url):
        raise ValueError('공식 출처 http(s) URL이 필요합니다.')
    stations = {r['station_id'] for r in rows}
    if station is None:
        if len(stations) != 1:
            raise ValueError('여러 관측소가 있습니다. --station을 지정하세요.')
        station = next(iter(stations))
    selected = sorted((r for r in rows if r['station_id'] == station), key=lambda r: r['observed_at'])
    if not selected:
        raise ValueError('선택한 관측소의 시간 자료가 없습니다.')
    by_day = defaultdict(list)
    for row in selected:
        by_day[row['observed_at'].date()].append(row)
    first, last = selected[0]['observed_at'].date(), selected[-1]['observed_at'].date()
    day = first
    included, excluded, temperatures = [], [], []
    missing_total = null_total = flagged_total = 0
    while day <= last:
        entries = by_day.get(day, [])
        expected = {datetime.combine(day, time(hour)) for hour in range(24)}
        actual = {r['observed_at'] for r in entries}
        if len(actual) != len(entries) or not actual <= expected:
            raise ValueError('중복 시각 또는 정시가 아닌 관측이 있습니다.')
        missing = len(expected - actual)
        nulls = sum(r['temperature_c'] is None for r in entries)
        flagged = sum(bool(r['quality_flag']) for r in entries)
        missing_total += missing
        null_total += nulls
        flagged_total += flagged
        if missing or nulls or flagged:
            excluded.append({'date': str(day), 'observed_hours': len(entries),
                'missing_timestamps': missing, 'null_temperatures': nulls, 'flagged_temperatures': flagged})
        else:
            included.append(str(day))
            temperatures.extend(r['temperature_c'] for r in entries)
        day += timedelta(days=1)
    if not temperatures:
        raise ValueError('정시 기온 24개가 모두 있는 완전한 날짜가 없습니다. 임의 보간하지 않습니다.')
    mean = sum(temperatures, Decimal(0)) / Decimal(len(temperatures))
    return {'kind': 'hourly_summary', 'station_id': station,
        'station_name': selected[0]['station_name'], 'timezone': timezone,
        'timezone_basis': 'ASOS 한국 현지시각으로 해석; CSV에는 UTC offset 없음',
        'metric': '완전한 날짜의 시간 관측 기온 산술평균', 'unit': '℃',
        'period_start': str(first), 'period_end': str(last),
        'mean_hourly_temperature_c': float(mean.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
        'coverage': {'total_calendar_days': (last - first).days + 1, 'total_rows': len(selected),
            'complete_days': len(included), 'excluded_days': len(excluded), 'used_hours': len(temperatures),
            'missing_timestamps': missing_total, 'null_temperatures': null_total,
            'flagged_temperatures': flagged_total},
        'included_dates': included, 'excluded_dates': excluded,
        'sources': [{'source_url': source_url, 'file_name': file_name, 'sha256': sha256}],
        'limitations': ['시간 관측 기온의 산술평균이며 기상청 공식 일평균기온·월평균기온이 아님',
            '자료 범위의 불완전한 날짜와 기온 결측·QC 플래그가 있는 날짜는 집계에서 제외함',
            '이 자료만으로 전년 대비 변화, 장기 기후변화, 변화 원인을 판단할 수 없음']}
