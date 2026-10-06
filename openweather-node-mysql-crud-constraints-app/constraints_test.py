"""실제 MySQL 제약 검증. 테스트 행은 마지막에 ROLLBACK."""
import os
import uuid
from pathlib import Path
import pymysql
from dotenv import load_dotenv
load_dotenv(Path(__file__).with_name('.env'))
conn = pymysql.connect(host=os.getenv('DB_HOST','127.0.0.1'), port=int(os.getenv('DB_PORT','3306')), user=os.getenv('DB_USER','root'), password=os.getenv('DB_PASSWORD',''), database=os.getenv('DB_NAME','weatherNewsDB'), autocommit=False)
# 실패해야 하는 SQL을 실행하고 실제 MySQL 오류 번호가 예상 제약조건과 일치하는지 검사합니다.
def reject(cur, sql, args, code):
    try:
        cur.execute(sql,args)
    except pymysql.MySQLError as e:
        assert e.args[0] == code, (code,e.args)
    else:
        raise AssertionError('제약 위반이 허용됨: '+sql)
try:
    with conn.cursor() as c:
        # 다른 실습 자료와 충돌하지 않도록 테스트 도시 코드에 UUID를 붙입니다.
        city='test_'+uuid.uuid4().hex[:12]
        ins='INSERT INTO weather_observation(city_code,region_name,temperature,humidity,wind_speed,observed_at) VALUES (%s,%s,%s,%s,%s,%s)'
        args=(city,'테스트',25,50,2,'2099-01-01 00:00:00')
        c.execute(ins,args); wid=c.lastrowid
        # 동일 도시/동일 관측 시각 재삽입: UNIQUE 위반을 확인합니다.
        reject(c,ins,args,1062) # UNIQUE
        # 이미 존재하는 weather_id 재사용: PK 중복 오류를 확인합니다.
        reject(c,'INSERT INTO weather_observation(weather_id,city_code,region_name,temperature,observed_at) VALUES (%s,%s,%s,%s,%s)',(wid,city,'테스트',25,'2099-01-02'),1062) # PK
        # 습도 101%: 0~100 범위 CHECK 위반이어야 합니다.
        reject(c,ins,(city,'테스트',25,101,2,'2099-01-03'),3819)
        # 음수 풍속: CHECK 위반이어야 합니다.
        reject(c,ins,(city,'테스트',25,50,-1,'2099-01-04'),3819)
        # 존재하지 않는 관측 ID: FK 위반이어야 합니다.
        reject(c,'INSERT INTO news_article(title,weather_id) VALUES (%s,%s)',('테스트',-1),1452)
        # 공백만 있는 제목: 제목 CHECK 위반이어야 합니다.
        reject(c,'INSERT INTO news_article(title) VALUES (%s)',('   ',),3819)
        c.execute('INSERT INTO news_article(title,weather_id) VALUES (%s,%s)',('테스트1',wid)); aid=c.lastrowid
        c.execute('INSERT INTO news_article(title,weather_id) VALUES (%s,%s)',('테스트2',wid)); aid2=c.lastrowid
        # 부모 관측 삭제 후 연결된 기사 2개도 없어지는지 CASCADE와 1:N 관계를 확인합니다.
        c.execute('DELETE FROM weather_observation WHERE weather_id=%s',(wid,))
        c.execute('SELECT COUNT(*) FROM news_article WHERE article_id IN (%s,%s)',(aid,aid2))
        assert c.fetchone()[0] == 0
        print('PASS: PK UNIQUE FK CHECK CASCADE / 1:N')
finally:
    # 성공/실패와 관계없이 테스트 행을 취소합니다. AUTO_INCREMENT 번호는 건너뛸 수 있습니다.
    conn.rollback()
    conn.close()
