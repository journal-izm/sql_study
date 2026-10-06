"""CSV 검증 → MySQL 저장 → 같은 달 비교 → 사람이 쓴 기사 저장. 가상 관측값을 포함하지 않습니다."""
import argparse
import calendar
import csv
import hashlib
import json
import os
import re
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

SOURCE_URL = 'https://data.kma.go.kr/data/grnd/selectAsosRltmList.do?pgmNo=36'
BASE = Path(__file__).resolve().parent


def connect():
    # DB를 사용할 때만 연결 라이브러리를 읽습니다.
    import pymysql
    from dotenv import load_dotenv
    load_dotenv(BASE / '.env')
    return pymysql.connect(host=os.getenv('MYSQL_HOST','127.0.0.1'),
        port=int(os.getenv('MYSQL_PORT','3306')), user=os.getenv('MYSQL_USER','root'),
        password=os.getenv('MYSQL_PASSWORD',''), database=os.getenv('MYSQL_DATABASE','weather_history_lab'),
        charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor, autocommit=False)


def normalize(value):
    # 열 이름의 공백, BOM, ℃/°C 표기 차이를 처리합니다.
    return re.sub(r'\s+', '', value.lstrip('\ufeff')).replace('°C','℃')


def read_csv(path, encoding=None):
    raw = Path(path).read_bytes()
    encodings = [encoding] if encoding else ['utf-8-sig','cp949']
    for enc in encodings:
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError('CSV 인코딩을 확인하세요. --encoding으로 지정할 수 있습니다.')
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        raise ValueError('CSV 헤더가 없습니다.')
    headers = {normalize(k): k for k in reader.fieldnames}
    def column(*names):
        for name in names:
            if name in headers:
                return headers[name]
        raise ValueError(f'필수 열 {names}이 없습니다. 실제 열: {reader.fieldnames}')
    sid_col = column('지점','station_id')
    name_col = column('지점명','station_name')
    day_col = column('일시','observed_date')
    temp_col = column('평균기온(℃)','avg_temp_c')
    rows, seen = [], set()
    names = {}
    for line, row in enumerate(reader, 2):
        if not any(v for v in row.values()):
            continue
        try:
            sid = int(row[sid_col].strip())
            name = row[name_col].strip()
            day = date.fromisoformat(row[day_col].strip())
            if sid <= 0 or not name or len(name) > 100:
                raise ValueError('관측소 코드/이름이 올바르지 않습니다.')
            if day > date.today():
                raise ValueError('미래 날짜의 관측값입니다.')
            value = row[temp_col].strip()
            temp = None if value in ('','NA','N/A','null','NULL','-') else Decimal(value)
            if temp is not None and (not temp.is_finite() or not -100 <= temp <= 100):
                raise ValueError('기온이 비정상입니다. 결측 코드와 단위를 확인하세요.')
            if temp is not None and temp != temp.quantize(Decimal('0.01')):
                raise ValueError('소수 2자리 초과 기온입니다. 원본 단위를 확인하세요.')
            key = (sid, day)
            if key in seen:
                raise ValueError('같은 관측소/날짜가 파일 안에서 중복됩니다.')
            if sid in names and names[sid] != name:
                raise ValueError('같은 지점 코드의 이름이 서로 다릅니다.')
            seen.add(key)
            names[sid] = name
            rows.append((sid, name, day, temp))
        except (ValueError, InvalidOperation, AttributeError, TypeError) as exc:
            raise ValueError(f'CSV {line}행 오류: {exc}') from exc
    if not rows:
        raise ValueError('관측 행이 없습니다.')
    return rows, hashlib.sha256(raw).hexdigest(), enc


def import_csv(args):
    rows, digest, encoding = read_csv(args.csv, args.encoding)
    print(f'검증 완료: {len(rows)}행, 인코딩 {encoding}, 결측 기온 {sum(r[3] is None for r in rows)}건')
    if args.validate_only:
        return
    # 전체 파일 단위 트랜잭션: 한 행이라도 실패하면 모두 취소합니다.
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT batch_id FROM import_batch WHERE sha256=%s',(digest,))
            if cur.fetchone():
                print('이미 가져온 동일 파일입니다. 저장을 생략합니다.')
                return
            cur.execute('INSERT INTO import_batch(file_name,sha256,source_url) VALUES(%s,%s,%s)',
                (Path(args.csv).name,digest,args.source_url))
            batch_id = cur.lastrowid
            inserted = skipped = 0
            for sid,name,day,temp in rows:
                cur.execute('SELECT station_name FROM station WHERE station_id=%s',(sid,))
                station = cur.fetchone()
                if station and station['station_name'] != name:
                    raise ValueError(f'지점 {sid}: DB와 CSV의 이름이 다릅니다.')
                if not station:
                    cur.execute('INSERT INTO station VALUES(%s,%s)',(sid,name))
                cur.execute('SELECT avg_temp_c FROM daily_weather WHERE station_id=%s AND observed_date=%s',(sid,day))
                existing = cur.fetchone()
                if existing:
                    if existing['avg_temp_c'] != temp:
                        raise ValueError(f'{sid}/{day}: 저장된 기온과 다릅니다. 원본 정정 여부를 확인하세요. 자동 덮어쓰기는 하지 않습니다.')
                    skipped += 1
                    continue
                cur.execute('INSERT INTO daily_weather(station_id,observed_date,avg_temp_c,batch_id) VALUES(%s,%s,%s,%s)',
                    (sid,day,temp,batch_id))
                inserted += 1
        conn.commit()
        print(f'저장 {inserted}행 / 동일 값 생략 {skipped}행 / batch_id={batch_id}')
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def summarize(rows, year, month):
    # 날짜 누락과 기온 NULL을 별도로 확인합니다. 부분 평균으로 월 평균 기사를 만들지 않습니다.
    expected = {date(year,month,d) for d in range(1,calendar.monthrange(year,month)[1]+1)}
    days = {r['observed_date'] for r in rows}
    missing = sorted(expected - days)
    null_days = sorted(r['observed_date'] for r in rows if r['avg_temp_c'] is None)
    if missing or null_days:
        raise ValueError(f'{year}-{month:02}: 누락 날짜 {[str(d) for d in missing]}, 결측 기온 {[str(d) for d in null_days]}')
    mean = sum((r['avg_temp_c'] for r in rows),Decimal(0))/Decimal(len(rows))
    return {'year':year,'month':month,'expected_days':len(expected),'valid_days':len(rows),
            'mean_daily_temperature_c':float(mean.quantize(Decimal('0.01'),rounding=ROUND_HALF_UP))},mean


def compare(args):
    if args.baseline_year == args.target_year:
        raise ValueError('서로 다른 두 해를 선택하세요.')
    end_day = date(args.target_year,args.month,calendar.monthrange(args.target_year,args.month)[1])
    if end_day >= date.today():
        raise ValueError('관측이 완료된 달을 선택하세요.')
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT station_name FROM station WHERE station_id=%s',(args.station,))
            station = cur.fetchone()
            if not station:
                raise ValueError('관측소가 없습니다. 먼저 CSV를 저장하세요.')
            summaries,means,sources = [],[],[]
            for year in [args.baseline_year,args.target_year]:
                first=date(year,args.month,1)
                last=date(year,args.month,calendar.monthrange(year,args.month)[1])
                cur.execute('SELECT w.observed_date,w.avg_temp_c,b.batch_id,b.file_name,b.sha256,b.source_url FROM daily_weather w JOIN import_batch b ON b.batch_id=w.batch_id WHERE w.station_id=%s AND w.observed_date BETWEEN %s AND %s ORDER BY w.observed_date',
                    (args.station,first,last))
                rows=cur.fetchall()
                summary,mean=summarize(rows,year,args.month)
                summaries.append(summary)
                means.append(mean)
                for row in rows:
                    source={key:row[key] for key in ['batch_id','file_name','sha256','source_url']}
                    if source not in sources:
                        sources.append(source)
            facts={'station_id':args.station,'station_name':station['station_name'],
                'metric':'일평균기온의 월 산술평균','unit':'℃','baseline':summaries[0], 'target':summaries[1],
                'difference_c':float((means[1]-means[0]).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)),
                'sources':sources,'limitations':['두 기간의 비교만으로 장기 기후변화나 변화 원인을 단정하지 않음','기상청 공식 월 통계와 산출·반올림 방식에 따라 차이가 있을 수 있음']}
            cur.execute('INSERT INTO analysis_result(station_id,baseline_year,target_year,target_month,fact_sheet) VALUES(%s,%s,%s,%s,%s)',
                (args.station,args.baseline_year,args.target_year,args.month,json.dumps(facts,ensure_ascii=False)))
            facts['analysis_id']=cur.lastrowid
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    output=Path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(facts,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(facts,ensure_ascii=False,indent=2))
    print(f'근거 저장: {output}')


def save_article(args):
    body=Path(args.body).read_text(encoding='utf-8-sig').strip()
    if not args.title.strip() or len(args.title.strip()) > 200 or not body:
        raise ValueError('제목 1~200자와 본문이 필요합니다.')
    conn=connect()
    try:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO news_article(analysis_id,title,lead_text,body_text,author_type) VALUES(%s,%s,%s,%s,%s)',
                (args.analysis_id,args.title.strip(),args.lead,body,'HUMAN'))
            article_id=cur.lastrowid
        conn.commit()
        print(f'기사 저장 완료: article_id={article_id}, status=DRAFT')
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    parser=argparse.ArgumentParser(description='과거 관측 CSV → MySQL → 같은 달 비교')
    sub=parser.add_subparsers(dest='command',required=True)
    imp=sub.add_parser('import-csv')
    imp.add_argument('csv')
    imp.add_argument('--encoding')
    imp.add_argument('--source-url',default=SOURCE_URL)
    imp.add_argument('--validate-only',action='store_true')
    imp.set_defaults(func=import_csv)
    comp=sub.add_parser('compare')
    comp.add_argument('--station',type=int,required=True)
    comp.add_argument('--baseline-year',type=int,required=True)
    comp.add_argument('--target-year',type=int,required=True)
    comp.add_argument('--month',type=int,choices=range(1,13),required=True)
    comp.add_argument('--output',default='data/results/fact_sheet.json')
    comp.set_defaults(func=compare)
    art=sub.add_parser('save-article')
    art.add_argument('--analysis-id',type=int,required=True)
    art.add_argument('--title',required=True)
    art.add_argument('--lead',default=None)
    art.add_argument('--body',required=True,help='사람이 작성한 UTF-8 본문 파일')
    art.set_defaults(func=save_article)
    args=parser.parse_args()
    try:
        args.func(args)
    except Exception as exc:
        parser.exit(1,f'실행 실패: {exc}\n')

if __name__=='__main__':
    main()
