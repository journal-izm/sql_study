"""PostgreSQL 어댑터·SQL 방언 계약. 실제 서버 통합 테스트와 구분합니다."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import weather_lab


class PostgreContractTests(unittest.TestCase):
    def test_connect_uses_psycopg_dict_rows_and_transaction(self):
        connect=MagicMock()
        factory=object()
        dotenv=SimpleNamespace(load_dotenv=MagicMock())
        with patch.dict(sys.modules, {'psycopg':SimpleNamespace(connect=connect),
                                     'psycopg.rows':SimpleNamespace(dict_row=factory), 'dotenv':dotenv}):
            weather_lab.connect()
        kwargs=connect.call_args.kwargs
        self.assertIs(kwargs['row_factory'],factory)
        self.assertFalse(kwargs['autocommit'])
        self.assertEqual(kwargs['connect_timeout'],10)
        self.assertNotIn('cursorclass',kwargs)

    def test_no_mysql_sql_or_lastrowid(self):
        root=Path(weather_lab.__file__).parent
        code=(root/'weather_lab.py').read_text(encoding='utf-8')
        schema=(root/'schema.sql').read_text(encoding='utf-8')
        queries=(root/'queries.sql').read_text(encoding='utf-8')
        for forbidden in ['lastrowid','pymysql','AUTO_INCREMENT','LONGTEXT','TINYINT','USE weather_history_lab','@station_id']:
            self.assertNotIn(forbidden,code+schema+queries)
        self.assertIn('RETURNING batch_id',code)
        self.assertIn('RETURNING analysis_id',code)
        self.assertIn('RETURNING article_id',code)
        self.assertIn('::jsonb',code)
        self.assertIn('JSONB',schema)
        self.assertIn('ON DELETE RESTRICT',schema)
        self.assertEqual(schema.count('CREATE TABLE IF NOT EXISTS'),6)

    def test_postgresql_parser_when_available(self):
        try:
            from pglast import parse_sql
        except ImportError:
            self.skipTest('선택 pglast 미설치: 실제 서버 검증을 대신하지 않습니다.')
        root=Path(weather_lab.__file__).parent
        for name in ('schema.sql','queries.sql'):
            with self.subTest(name=name):
                self.assertTrue(parse_sql((root/name).read_text(encoding='utf-8')))


if __name__ == '__main__':
    unittest.main()
