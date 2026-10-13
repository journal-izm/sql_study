"""선택 실서버 테스트. RUN_POSTGRE_INTEGRATION=1 및 PG* 접속 설정 필요.

이 테스트가 만든 고유 weather_test_* 스키마에서만 가상 관측을 사용하고 종료 시
그 스키마를 삭제합니다. 실제 수업 데이터 테이블에는 쓰지 않습니다.
"""
import csv
import io
import json
import os
import tempfile
import unittest
import uuid
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import weather_lab as lab
from article_generation import create_draft


@unittest.skipUnless(os.getenv('RUN_POSTGRE_INTEGRATION') == '1', '선택 PostgreSQL 실서버 테스트')
class PostgreIntegrationTests(unittest.TestCase):
    def test_full_daily_flow_constraints_queries_and_rollback(self):
        import psycopg
        from dotenv import load_dotenv
        load_dotenv(Path(lab.__file__).parent / '.env')
        from psycopg import sql
        from psycopg.rows import dict_row
        schema = 'weather_test_' + uuid.uuid4().hex
        config = {'host':os.getenv('PGHOST','127.0.0.1'), 'port':int(os.getenv('PGPORT','5432')),
                  'user':os.getenv('PGUSER','postgres'), 'password':os.getenv('PGPASSWORD',''),
                  'dbname':os.getenv('PGDATABASE','weather_history_lab'), 'connect_timeout':10}
        admin = psycopg.connect(**config, autocommit=True, row_factory=dict_row)
        def connect():
            conn=psycopg.connect(**config,row_factory=dict_row)
            conn.execute(sql.SQL('SET search_path TO {}, pg_catalog').format(sql.Identifier(schema)))
            return conn
        try:
            admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            admin.execute(sql.SQL('SET search_path TO {}, pg_catalog').format(sql.Identifier(schema)))
            admin.execute((Path(lab.__file__).parent/'schema.sql').read_text(encoding='utf-8'))
            tables=admin.execute('SELECT table_name FROM information_schema.tables WHERE table_schema=%s',(schema,)).fetchall()
            self.assertEqual(len(tables),6)
            with tempfile.TemporaryDirectory() as directory, patch.object(lab,'connect',side_effect=connect), redirect_stdout(io.StringIO()):
                root=Path(directory)
                data=root/'synthetic_test_only.csv'
                with data.open('w',encoding='utf-8',newline='') as handle:
                    writer=csv.writer(handle)
                    writer.writerow(['station_id','station_name','observed_date','avg_temp_c'])
                    for year,temp in [(2025,'20.00'),(2026,'21.50')]:
                        for day in range(1,31):writer.writerow([108,'서울',f'{year}-09-{day:02}',temp])
                args=Namespace(csv=str(data),encoding=None,validate_only=False,source_url='https://example.invalid/synthetic-test-only')
                lab.import_csv(args)
                lab.import_csv(args)
                self.assertEqual(admin.execute('SELECT COUNT(*) AS n FROM daily_weather').fetchone()['n'],60)
                self.assertEqual(admin.execute('SELECT COUNT(*) AS n FROM import_batch').fetchone()['n'],1)
                # 파일 내 한 값이 바뀌면 새 batch와 모든 쓰기가 함께 취소되어야 합니다.
                changed=root/'conflict.csv';changed.write_text(data.read_text(encoding='utf-8').replace('20.00','19.00',1),encoding='utf-8')
                with self.assertRaises(ValueError):lab.import_csv(Namespace(**{**vars(args),'csv':str(changed)}))
                self.assertEqual(admin.execute('SELECT COUNT(*) AS n FROM import_batch').fetchone()['n'],1)
                output=root/'facts.json'
                lab.compare(Namespace(station=108,baseline_year=2025,target_year=2026,month=9,output=str(output)))
                exported=json.loads(output.read_text(encoding='utf-8'))
                self.assertEqual(exported['difference_c'],1.5)
                analysis_id=exported['analysis_id']
                facts=lab.load_analysis(analysis_id)
                article_id=lab.save_generated_draft(analysis_id,create_draft(facts))
                self.assertEqual(admin.execute('SELECT author_type,status FROM news_article WHERE article_id=%s',(article_id,)).fetchone(),{'author_type':'TEMPLATE','status':'DRAFT'})
                self.assertEqual(admin.execute('SELECT generation_mode FROM article_generation').fetchone()['generation_mode'],'template')
                body=root/'human.txt';body.write_text('가상 관측을 사용한 테스트 전용 본문',encoding='utf-8')
                lab.save_article(Namespace(analysis_id=analysis_id,title='가상 테스트',lead=None,body=str(body)))
                self.assertEqual(admin.execute('SELECT COUNT(*) AS n FROM news_article').fetchone()['n'],2)
                # FK와 RESTRICT는 실제 서버가 거부하는지 확인합니다.
                with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                    admin.execute('DELETE FROM analysis_result WHERE analysis_id=%s',(analysis_id,))
                with self.assertRaises(psycopg.errors.CheckViolation):
                    admin.execute("INSERT INTO news_article(analysis_id,title,body_text,author_type) VALUES(%s,'x','x','BAD')",(analysis_id,))
                with self.assertRaises(psycopg.errors.UniqueViolation):
                    admin.execute("INSERT INTO station VALUES(108,'중복')")
                # 배포할 SQL 파일의 모든 문장을 실제 서버에서 실행하고 Python 계산과 대조합니다.
                cursor=admin.cursor()
                cursor.execute((Path(lab.__file__).parent/'queries.sql').read_text(encoding='utf-8'))
                comparison=None
                while True:
                    if cursor.description:
                        rows=cursor.fetchall()
                        if rows and 'difference_c' in rows[0]:comparison=rows[0]
                    if not cursor.nextset():break
                self.assertIsNotNone(comparison)
                self.assertEqual(float(comparison['difference_c']),1.5)
                self.assertEqual(float(comparison['baseline_mean_c']),20.0)
                self.assertEqual(float(comparison['target_mean_c']),21.5)
        finally:
            admin.execute('SET search_path TO public, pg_catalog')
            admin.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
            admin.close()


if __name__ == '__main__':
    unittest.main()
