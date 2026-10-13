"""DB 연결/모델 호출 없는 명령·트랜잭션 계약 검사. 수치는 가상 테스트 값입니다."""
import io
import json
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

import weather_lab as lab
from article_generation import create_draft
from test_article_generation import facts_fixture


class StorageTests(unittest.TestCase):
    def connection(self, current=None):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.lastrowid = 42
        # PostgreSQL의 RETURNING과 MySQL의 lastrowid를 같은 계약으로 검사합니다.
        def execute(sql, params=None):
            cursor.current_sql = sql
        cursor.execute.side_effect = execute
        def fetchone():
            if 'RETURNING' in cursor.current_sql:
                name = cursor.current_sql.rsplit('RETURNING', 1)[1].strip()
                return {name: 42}
            return {'fact_sheet': current} if current is not None else None
        cursor.fetchone.side_effect = fetchone
        return connection, cursor

    def test_load_analysis_decodes_json(self):
        facts=facts_fixture()
        conn, cur=self.connection(json.dumps(facts))
        with patch.object(lab,'connect',return_value=conn):
            self.assertEqual(lab.load_analysis(9),facts)
        self.assertEqual(cur.execute.call_args.args[1], (9,))
        conn.close.assert_called_once()

    def test_load_missing_closes(self):
        conn, _=self.connection()
        with patch.object(lab,'connect',return_value=conn), self.assertRaises(ValueError):
            lab.load_analysis(9)
        conn.close.assert_called_once()

    def test_save_generated_atomic_and_author_type(self):
        draft=create_draft(facts_fixture())
        conn, cur=self.connection(draft['facts'])
        with patch.object(lab,'connect',return_value=conn):
            self.assertEqual(lab.save_generated_draft(9,draft),42)
        calls=cur.execute.call_args_list
        self.assertIn('FOR UPDATE',calls[0].args[0])
        self.assertEqual(calls[1].args[1][-1],'TEMPLATE')
        self.assertIn('INSERT INTO article_generation',calls[2].args[0])
        self.assertEqual(calls[2].args[1][1],'template')
        conn.commit.assert_called_once()
        conn.rollback.assert_not_called()
        conn.close.assert_called_once()

    def test_changed_facts_abort_before_article_insert(self):
        draft=create_draft(facts_fixture())
        conn, cur=self.connection(dict(draft['facts'], station_name='다른 이름'))
        with patch.object(lab,'connect',return_value=conn), self.assertRaisesRegex(ValueError,'변경'):
            lab.save_generated_draft(9,draft)
        self.assertEqual(cur.execute.call_count,1)
        conn.commit.assert_not_called()
        conn.rollback.assert_called_once()
        conn.close.assert_called_once()

    def test_second_insert_failure_rolls_back_article(self):
        draft=create_draft(facts_fixture())
        conn, cur=self.connection(draft['facts'])
        execute=cur.execute.side_effect
        def failure(sql,params=None):
            if 'INSERT INTO article_generation' in sql:
                raise RuntimeError('simulated database failure')
            return execute(sql,params)
        cur.execute.side_effect=failure
        with patch.object(lab,'connect',return_value=conn), self.assertRaises(RuntimeError):
            lab.save_generated_draft(9,draft)
        conn.commit.assert_not_called()
        conn.rollback.assert_called_once()
        conn.close.assert_called_once()

    def test_human_save_keeps_existing_contract(self):
        conn, cur=self.connection()
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'human.txt';p.write_text('사람이 작성한 본문',encoding='utf-8')
            args=Namespace(body=str(p),title='사람 제목',lead=None,analysis_id=9)
            with patch.object(lab,'connect',return_value=conn), redirect_stdout(io.StringIO()):
                lab.save_article(args)
        self.assertEqual(cur.execute.call_args.args[1][-1],'HUMAN')
        conn.commit.assert_called_once()


class CliTests(unittest.TestCase):
    def args(self, facts, output, **extra):
        result=Namespace(facts=str(facts),output=str(output),analysis_id=None,save_to_db=False,
                         mode='template',model=None,max_tokens=900,timeout=60,overwrite=False)
        for k,v in extra.items():setattr(result,k,v)
        return result

    def test_file_generation_without_db(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'facts.json';source.write_text(json.dumps(facts_fixture()),encoding='utf-8')
            output=Path(d)/'out.json'
            with patch.object(lab,'connect',side_effect=AssertionError('must not connect')),redirect_stdout(io.StringIO()):
                lab.generate_article(self.args(source,output))
            self.assertEqual(json.loads(output.read_text(encoding='utf-8'))['mode'],'template')
            self.assertIn('DRAFT',output.with_suffix('.txt').read_text(encoding='utf-8'))

    def test_file_input_cannot_write_db(self):
        with self.assertRaisesRegex(ValueError,'analysis-id'):
            lab.generate_article(self.args('no-file.json','unused.json',save_to_db=True))

    def test_existing_output_prevents_paid_call(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'existing.json';p.write_text('old draft',encoding='utf-8')
            with patch('article_generation.create_draft') as generate, self.assertRaisesRegex(ValueError,'이미'):
                lab.generate_article(self.args('no-file.json',p,mode='openai'))
            generate.assert_not_called()
            self.assertEqual(p.read_text(encoding='utf-8'),'old draft')

    def test_input_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'facts.json';p.write_text(json.dumps(facts_fixture()),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'근거 입력'):
                lab.generate_article(self.args(p,p,overwrite=True))

    def test_wrong_hourly_input_explains_route(self):
        p=Path(__file__).parent/'fixtures'/'asos_hourly_seoul_20260901_03.csv'
        with self.assertRaisesRegex(ValueError,'summarize-hourly'):
            lab.read_csv(p)


class OutputSafetyTests(unittest.TestCase):
    def test_hourly_source_path_and_symlink_are_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'source.csv';source.write_text('원본 보존',encoding='utf-8')
            outputs=[source]
            link=Path(d)/'linked.json'
            try:
                link.symlink_to(source)
            except (OSError,NotImplementedError):
                # Windows에서는 일반 계정의 심볼릭 링크 생성 권한이 없을 수 있습니다.
                pass
            else:
                outputs.append(link)
            for output in outputs:
                args=Namespace(csv=str(source),output=str(output),overwrite=True,encoding=None,
                               station=None,timezone='Asia/Seoul',source_url='https://data.kma.go.kr/')
                with self.subTest(output=output), self.assertRaisesRegex(ValueError,'원본 CSV'):
                    lab.summarize_hourly_command(args)
            self.assertEqual(source.read_text(encoding='utf-8'),'원본 보존')

    def test_hourly_existing_facts_require_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'facts.json';target.write_text('기존 근거',encoding='utf-8')
            args=Namespace(csv='missing.csv',output=str(target),overwrite=False,encoding=None,
                           station=None,timezone='Asia/Seoul',source_url='https://data.kma.go.kr/')
            with self.assertRaisesRegex(ValueError,'이미'):
                lab.summarize_hourly_command(args)
            self.assertEqual(target.read_text(encoding='utf-8'),'기존 근거')

    def test_unwritable_parent_and_nonfile_prevent_paid_call(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'facts.json';source.write_text(json.dumps(facts_fixture()),encoding='utf-8')
            parent=Path(d)/'not-a-directory';parent.write_text('old',encoding='utf-8')
            directory=Path(d)/'is-a-directory.json';directory.mkdir()
            for output in (parent/'out.json',directory):
                args=CliTests().args(source,output,mode='openai',overwrite=True)
                with patch('article_generation.create_draft') as generate:
                    with self.assertRaises((ValueError,FileExistsError,NotADirectoryError)):
                        lab.generate_article(args)
                    generate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
