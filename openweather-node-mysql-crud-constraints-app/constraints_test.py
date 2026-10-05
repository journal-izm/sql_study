"""실제 MySQL 제약 검증. 테스트 행은 마지막에 ROLLBACK."""
import os
import uuid
from pathlib import Path
import pymysql
from dotenv import load_dotenv
load_dotenv(Path(__file__).with_name('.env'))
conn = pymysql.connect(host=os.getenv('DB_HOST','127.0.0.1'), port=int(os.getenv('DB_PORT','3306')), user=os.getenv('DB_USER','root'), password=os.getenv('DB_PASSWORD',''), database=os.getenv('DB_NAME','weatherNewsDB'), autocommit=False)
def reject(cur, sql, args, code):
    try:
        cur.execute(sql,args)
    except pymysql.MySQLError as e:
        assert e.args[0] == code, (code,e.args)
    else:
        raise AssertionError('제약 위반이 허용됨: '+sql)
try:
    with conn.cursor() as c:
        city='test_'+uuid.uuid4().hex[:12]
        ins='INSERT INTO weather_observation(city_code,region_name,temperature,humidity,wind_speed,observed_at) VALUES (%s,%s,%s,%s,%s,%s)'
        args=(city,'테스트',25,50,2,'2099-01-01 00:00:00')
        c.execute(ins,args); wid=c.lastrowid
        reject(c,ins,args,1062) # UNIQUE
        reject(c,'INSERT INTO weather_observation(weather_id,city_code,region_name,temperature,observed_at) VALUES (%s,%s,%s,%s,%s)',(wid,city,'테스트',25,'2099-01-02'),1062) # PK
        reject(c,ins,(city,'테스트',25,101,2,'2099-01-03'),3819)
        reject(c,ins,(city,'테스트',25,50,-1,'2099-01-04'),3819)
        reject(c,'INSERT INTO news_article(title,weather_id) VALUES (%s,%s)',('테스트',-1),1452)
        reject(c,'INSERT INTO news_article(title) VALUES (%s)',('   ',),3819)
        c.execute('INSERT INTO news_article(title,weather_id) VALUES (%s,%s)',('테스트1',wid)); aid=c.lastrowid
        c.execute('INSERT INTO news_article(title,weather_id) VALUES (%s,%s)',('테스트2',wid)); aid2=c.lastrowid
        c.execute('DELETE FROM weather_observation WHERE weather_id=%s',(wid,))
        c.execute('SELECT COUNT(*) FROM news_article WHERE article_id IN (%s,%s)',(aid,aid2))
        assert c.fetchone()[0] == 0
        print('PASS: PK UNIQUE FK CHECK CASCADE / 1:N')
finally:
    conn.rollback()
    conn.close()
