"""CSV 검증 → MySQL 저장 → 같은 달 비교 → 근거 기반 기사 초안. 가상 관측값을 포함하지 않습니다."""
import argparse
import calendar
import csv
import hashlib
import io
import json
import os
import re
import tempfile
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

SOURCE_URL = 'https://data.kma.go.kr/data/grnd/selectAsosRltmList.do?pgmNo=36'
BASE = Path(__file__).resolve().parent


# 환경변수로 MySQL 연결을 만듭니다. 비밀번호를 소스에 직접 쓰지 않습니다.
def connect():
    # DB를 사용할 때만 연결 라이브러리를 읽습니다.
    import pymysql
    from dotenv import load_dotenv
    # 현재 파일 폴더의 .env를 읽어 실행 위치가 달라도 설정을 찾습니다.
    load_dotenv(BASE / '.env')
    return pymysql.connect(host=os.getenv('MYSQL_HOST','127.0.0.1'),
        port=int(os.getenv('MYSQL_PORT','3306')), user=os.getenv('MYSQL_USER','root'),
        password=os.getenv('MYSQL_PASSWORD',''), database=os.getenv('MYSQL_DATABASE','weather_history_lab'),
        charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor, autocommit=False)


# CSV 열 이름만 정규화합니다. 관측값을 바꾸는 함수는 아닙니다.
def normalize(value):
    # 열 이름의 공백, BOM, ℃/°C 표기 차이를 처리합니다.
    return re.sub(r'\s+', '', value.lstrip('\ufeff')).replace('°C','℃')


# CSV 전체를 먼저 검사합니다. 이 함수는 DB에 저장하지 않고 검증된 행과 파일 해시를 반환합니다.
def read_csv(path, encoding=None):
    raw = Path(path).read_bytes()
    # UTF-8 BOM을 먼저 시도하고 실패하면 CP949를 시도합니다. 원본 한글 CSV 인코딩에 대응합니다.
    encodings = [encoding] if encoding else ['utf-8-sig','cp949']
    for enc in encodings:
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError('CSV 인코딩을 확인하세요. --encoding으로 지정할 수 있습니다.')
    # 첫 줄을 열 이름으로 읽어 각 데이터 행을 딕셔너리로 만듭니다.
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError('CSV 헤더가 없습니다.')
    normalized_headers = [normalize(k) for k in reader.fieldnames]
    if len(set(normalized_headers)) != len(normalized_headers):
        raise ValueError('중복된 CSV 열 이름이 있습니다.')
    headers = dict(zip(normalized_headers, reader.fieldnames))
    if '기온(℃)' in headers and '평균기온(℃)' not in headers:
        raise ValueError('시간 관측 CSV입니다. 일평균기온으로 바꾸지 마세요. summarize-hourly 명령을 사용하세요.')
    def column(*names):
        for name in names:
            if name in headers:
                return headers[name]
        raise ValueError(f'필수 열 {names}이 없습니다. 실제 열: {reader.fieldnames}')
    sid_col = column('지점','station_id')
    name_col = column('지점명','station_name')
    day_col = column('일시','observed_date')
    temp_col = column('평균기온(℃)','avg_temp_c')
    # 행 목록과 중복검사용 집합을 초기화합니다. 같은 관측소/날짜는 한 번만 허용합니다.
    rows, seen = [], set()
    names = {}
    for line, row in enumerate(reader, 2):
        if not any(v for v in row.values()):
            continue
        try:
            if None in row or any(v is None for v in row.values()):
                raise ValueError('CSV 열 개수가 헤더와 다릅니다.')
            sid = int(row[sid_col].strip())
            name = row[name_col].strip()
            if ' ' in row[day_col].strip() or 'T' in row[day_col].strip():
                raise ValueError('시간 자료입니다. 일자료를 받거나 summarize-hourly를 사용하세요.')
            day = date.fromisoformat(row[day_col].strip())
            if sid <= 0 or not name or len(name) > 100:
                raise ValueError('관측소 코드/이름이 올바르지 않습니다.')
            if day > date.today():
                raise ValueError('미래 날짜의 관측값입니다.')
            value = row[temp_col].strip()
            # 빈 값은 None으로 유지합니다. 0℃는 유효한 관측값이므로 결측과 구분합니다.
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


# 검증된 원본 한 파일을 한 트랜잭션으로 가져옵니다. 중간 실패 시 일부 행만 남지 않게 합니다.
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
                # 이미 저장된 같은 날짜의 행을 찾습니다. 동일 값은 생략하고 다른 값은 정정 여부를 확인합니다.
                existing = cur.fetchone()
                if existing:
                    if existing['avg_temp_c'] != temp:
                        raise ValueError(f'{sid}/{day}: 저장된 기온과 다릅니다. 원본 정정 여부를 확인하세요. 자동 덮어쓰기는 하지 않습니다.')
                    skipped += 1
                    continue
                cur.execute('INSERT INTO daily_weather(station_id,observed_date,avg_temp_c,batch_id) VALUES(%s,%s,%s,%s)',
                    (sid,day,temp,batch_id))
                inserted += 1
        # 쓰기 작업을 확정합니다. 이 줄 전의 작업은 실패 시 rollback할 수 있습니다.
        conn.commit()
        print(f'저장 {inserted}행 / 동일 값 생략 {skipped}행 / batch_id={batch_id}')
    except Exception:
        # 이번 트랜잭션의 쓰기를 취소하고 원래 오류를 상위 호출자에게 전달합니다.
        conn.rollback()
        raise
    finally:
        # 연결을 반환/종료합니다. 성공해도 오류가 나도 finally에서 정리합니다.
        conn.close()


# 해당 월의 모든 날짜가 있는지 먼저 확인하고 일평균기온들의 산술평균을 계산합니다.
def summarize(rows, year, month):
    # 날짜 누락과 기온 NULL을 별도로 확인합니다. 부분 평균으로 월 평균 기사를 만들지 않습니다.
    # 달력으로 해당 월의 모든 날짜를 만들어 실제 데이터와 대조합니다.
    expected = {date(year,month,d) for d in range(1,calendar.monthrange(year,month)[1]+1)}
    days = {r['observed_date'] for r in rows}
    # 행 자체가 없는 날짜를 찾습니다. 행은 있지만 기온 NULL인 경우와 따로 보고합니다.
    if len(days) != len(rows) or not days <= expected:
        raise ValueError('중복 날짜 또는 선택한 월 밖의 관측이 있습니다.')
    missing = sorted(expected - days)
    null_days = sorted(r['observed_date'] for r in rows if r['avg_temp_c'] is None)
    if missing or null_days:
        raise ValueError(f'{year}-{month:02}: 누락 날짜 {[str(d) for d in missing]}, 결측 기온 {[str(d) for d in null_days]}')
    # Decimal로 일평균기온을 합산하고 일수로 나눕니다. 계산 중 반올림은 하지 않습니다.
    mean = sum((r['avg_temp_c'] for r in rows),Decimal(0))/Decimal(len(rows))
    return {'year':year,'month':month,'expected_days':len(expected),'valid_days':len(rows),
            'mean_daily_temperature_c':float(mean.quantize(Decimal('0.01'),rounding=ROUND_HALF_UP))},mean


# 같은 관측소/같은 월의 두 해를 비교하고 기사 작성 당시 근거를 JSON으로 보존합니다.
def compare(args):
    if args.baseline_year == args.target_year:
        raise ValueError('서로 다른 두 해를 선택하세요.')
    for year in (args.baseline_year, args.target_year):
        if not 1904 <= year <= 9999:
            raise ValueError('1904~9999년 범위를 선택하세요.')
        end_day = date(year,args.month,calendar.monthrange(year,args.month)[1])
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
            # AI나 사람이 읽을 사실 묶음입니다. 수치와 함께 지역/기간/단위/출처/해석 한계를 저장합니다.
            facts={'station_id':args.station,'station_name':station['station_name'],
                'metric':'일평균기온의 월 산술평균','unit':'℃','baseline':summaries[0], 'target':summaries[1],
                'difference_c':float((means[1]-means[0]).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)),
                'sources':sources,'limitations':['두 기간의 비교만으로 장기 기후변화나 변화 원인을 단정하지 않음','기상청 공식 월 통계와 산출·반올림 방식에 따라 차이가 있을 수 있음']}
            cur.execute('INSERT INTO analysis_result(station_id,baseline_year,target_year,target_month,fact_sheet) VALUES(%s,%s,%s,%s,%s)',
                (args.station,args.baseline_year,args.target_year,args.month,json.dumps(facts,ensure_ascii=False)))
            facts['analysis_id']=cur.lastrowid
        # 쓰기 작업을 확정합니다. 이 줄 전의 작업은 실패 시 rollback할 수 있습니다.
        conn.commit()
    except Exception:
        # 이번 트랜잭션의 쓰기를 취소하고 원래 오류를 상위 호출자에게 전달합니다.
        conn.rollback()
        raise
    finally:
        # 연결을 반환/종료합니다. 성공해도 오류가 나도 finally에서 정리합니다.
        conn.close()
    output=Path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    # DB 결과를 UTF-8 JSON 파일로도 저장해 수업 검토와 다음 단계 기사 생성에 사용합니다.
    output.write_text(json.dumps(facts,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(facts,ensure_ascii=False,indent=2))
    print(f'근거 저장: {output}')


# 사람이 작성한 본문을 분석 ID에 연결합니다. HUMAN/DRAFT는 작성자 구분과 검토 전 상태입니다.
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
        # 쓰기 작업을 확정합니다. 이 줄 전의 작업은 실패 시 rollback할 수 있습니다.
        conn.commit()
        print(f'기사 저장 완료: article_id={article_id}, status=DRAFT')
    except Exception:
        # 이번 트랜잭션의 쓰기를 취소하고 원래 오류를 상위 호출자에게 전달합니다.
        conn.rollback()
        raise
    finally:
        # 연결을 반환/종료합니다. 성공해도 오류가 나도 finally에서 정리합니다.
        conn.close()


def summarize_hourly_command(args):
    from hourly_weather import read_hourly_csv, summarize_hourly
    output = Path(args.output)
    if Path(args.csv).resolve() == output.resolve():
        raise ValueError('원본 CSV를 근거 출력으로 덮어쓸 수 없습니다.')
    if output.exists() and not args.overwrite:
        raise ValueError('출력 파일이 이미 있습니다. 다른 --output 또는 --overwrite를 지정하세요.')
    rows, digest, encoding = read_hourly_csv(args.csv, args.encoding)
    facts = summarize_hourly(rows, source_url=args.source_url, file_name=Path(args.csv).name,
                             sha256=digest, station=args.station, timezone=args.timezone)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'시간 CSV 검증 완료: {encoding}, 완전한 {facts["coverage"]["complete_days"]}일 / 제외 {facts["coverage"]["excluded_days"]}일')
    print(f'시간 관측 근거 저장: {output} (일자료 DB에는 저장하지 않음)')


def load_analysis(analysis_id):
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT fact_sheet FROM analysis_result WHERE analysis_id=%s', (analysis_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError('analysis_id에 해당하는 근거가 없습니다.')
            facts = row['fact_sheet']
            return json.loads(facts) if isinstance(facts, (str, bytes)) else facts
    finally:
        conn.close()


def save_generated_draft(analysis_id, draft):
    """DB에서 읽은 근거로 만든 초안만 저장합니다. 두 INSERT는 한 트랜잭션입니다."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            # 모델 호출 동안 분석 근거가 수정되었으면 연결하지 않습니다.
            cur.execute('SELECT fact_sheet FROM analysis_result WHERE analysis_id=%s FOR UPDATE', (analysis_id,))
            row = cur.fetchone()
            current = row['fact_sheet'] if row else None
            if isinstance(current, (str, bytes)):
                current = json.loads(current)
            if current != draft['facts']:
                raise ValueError('분석 근거가 변경되었거나 없습니다. 새 근거로 다시 생성하세요.')
            a = draft['article']
            author = 'TEMPLATE' if draft['mode'] == 'template' else 'AI'
            cur.execute('INSERT INTO news_article(analysis_id,title,lead_text,body_text,author_type) VALUES(%s,%s,%s,%s,%s)',
                        (analysis_id,a['title'],a['lead'],a['body'],author))
            article_id = cur.lastrowid
            cur.execute('INSERT INTO article_generation(article_id,generation_mode,model_name,prompt_version,fact_snapshot,facts_sha256,validation_checks) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                        (article_id,draft['mode'],(draft['model'] + '@' + draft['model_revision']) if draft.get('model_revision') else draft['model'],draft['prompt_version'],
                         json.dumps(draft['facts'],ensure_ascii=False),draft['facts_sha256'],
                         json.dumps(draft['checks'],ensure_ascii=False)))
        conn.commit()
        return article_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def generate_article(args):
    from article_generation import create_draft, render_draft
    # template/CSV-only는 외부 패키지가 없어도 실행됩니다. .env는 있으면 읽습니다.
    try:
        from dotenv import load_dotenv
    except ImportError:
        pass
    else:
        load_dotenv(BASE / '.env')
    if args.save_to_db and args.analysis_id is None:
        raise ValueError('--save-to-db는 --analysis-id로 DB 근거를 읽은 경우에만 가능합니다.')
    output = Path(args.output)
    text_output = output.with_suffix('.txt')
    if text_output == output:
        text_output = output.with_name(output.name + '.txt')
    if not args.overwrite and (output.exists() or text_output.exists()):
        raise ValueError('출력 파일이 이미 있습니다. 다른 --output을 선택하거나 --overwrite를 지정하세요.')
    if args.facts and Path(args.facts).resolve() in (output.resolve(), text_output.resolve()):
        raise ValueError('근거 입력 파일을 기사 출력으로 덮어쓸 수 없습니다.')
    # 유료 호출 전에 디렉터리/파일 종류/쓰기 권한을 확인합니다.
    for target in (output, text_output):
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise ValueError('출력은 일반 파일 경로여야 합니다. 링크/디렉터리를 지정하지 마세요.')
        if target.exists() and not os.access(target, os.W_OK):
            raise ValueError('출력 파일에 쓰기 권한이 없습니다.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=output.parent) as probe:
        probe.write(b'output permission check')
    if args.analysis_id is not None:
        facts = load_analysis(args.analysis_id)
    else:
        facts = json.loads(Path(args.facts).read_text(encoding='utf-8-sig'))
    draft = create_draft(facts, args.mode, args.model, args.max_tokens, args.timeout)
    output.parent.mkdir(parents=True, exist_ok=True)
    # 먼저 파일을 보존합니다. DB 저장 실패 시에도 생성된 유료 응답을 잃지 않습니다.
    output.write_text(json.dumps(draft,ensure_ascii=False,indent=2),encoding='utf-8')
    text_output.write_text(render_draft(draft), encoding='utf-8')
    print(f'DRAFT 저장: {output}, {text_output}; 숫자 보조 검사는 전체 사실 검증이 아닙니다.')
    if args.save_to_db:
        article_id = save_generated_draft(args.analysis_id, draft)
        print(f'기사 DB 저장 완료: article_id={article_id}, status=DRAFT')


# 기존 명령은 유지하고 시간 CSV 집계와 세 가지 초안 모드를 추가합니다.
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
    hourly=sub.add_parser('summarize-hourly',help='시간 CSV만 별도 집계; 일자료 DB에 저장하지 않음')
    hourly.add_argument('csv')
    hourly.add_argument('--encoding')
    hourly.add_argument('--station',type=int)
    hourly.add_argument('--timezone',choices=['Asia/Seoul'],default='Asia/Seoul')
    hourly.add_argument('--source-url',default=SOURCE_URL)
    hourly.add_argument('--output',default='data/results/hourly_facts.json')
    hourly.add_argument('--overwrite',action='store_true',help='기존 근거 출력 파일 교체 허용')
    hourly.set_defaults(func=summarize_hourly_command)
    gen=sub.add_parser('generate-article',help='근거에서 template/huggingface/openai 초안 생성')
    source=gen.add_mutually_exclusive_group(required=True)
    source.add_argument('--facts',help='근거 JSON; 파일 출력만 가능')
    source.add_argument('--analysis-id',type=int,help='DB에 저장된 월 비교 근거 ID')
    gen.add_argument('--mode',choices=['template','huggingface','openai'],default='template')
    gen.add_argument('--model',help='선택한 공급자의 모델 ID; 기본값은 .env.example 참고')
    gen.add_argument('--max-tokens',type=int,default=900)
    gen.add_argument('--timeout',type=float,default=60,help='OpenAI 요청 제한 시간(초)')
    gen.add_argument('--output',default='data/results/generated_article.json')
    gen.add_argument('--overwrite',action='store_true',help='기존 출력 파일 교체 허용')
    gen.add_argument('--save-to-db',action='store_true',help='월 비교 근거로 만든 DRAFT를 DB에도 저장')
    gen.set_defaults(func=generate_article)
    args=parser.parse_args()
    try:
        args.func(args)
    except Exception as exc:
        parser.exit(1,f'실행 실패: {exc}\n')

if __name__=='__main__':
    main()

