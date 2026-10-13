"""실제 48행 fixture와 SDK mock만 사용. 유료 API/모델 다운로드/DB 접속 없음."""
import hashlib
import json
import os
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import httpx
import openai
import app
import article_generation as ag
import start_api


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = TestClient(app.app)
        self.addCleanup(self.client.close)

    def test_home_health_and_docs(self):
        self.assertIn('날씨 데이터 기사 실습', self.client.get('/').text)
        self.assertEqual(self.client.get('/docs').status_code, 200)
        spec = self.client.get('/openapi.json').json()
        self.assertIn('/articles', spec['paths'])
        self.assertIn('/facts', spec['paths'])
        health = self.client.get('/health').json()
        self.assertFalse(health['live_api_verified'])
        self.assertFalse(health['openai_configured'])
        self.assertFalse(health['huggingface_enabled'])
        self.assertEqual(health['openai_model'], 'gpt-5.4-mini-2026-03-17')
        self.assertEqual(health['dataset'], 'bundled_48_rows')

    def test_real_fixture_preflight_and_template(self):
        with patch.object(ag, 'generate_openai') as paid, patch.object(ag, 'generate_huggingface') as hf:
            facts = self.client.get('/facts').json()
            response = self.client.post('/articles', json={'mode': 'template'})
        self.assertEqual(response.status_code, 200, response.text)
        draft = response.json()
        self.assertEqual(facts['coverage']['total_rows'], 48)
        self.assertEqual(facts['coverage']['complete_days'], 1)
        self.assertEqual(facts['coverage']['excluded_days'], 2)
        self.assertEqual(facts['coverage']['used_hours'], 24)
        self.assertEqual(facts['included_dates'], ['2026-09-02'])
        self.assertEqual(facts['mean_hourly_temperature_c'], 24.64)
        self.assertEqual(draft['facts'], facts)
        canonical = json.dumps(facts, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        self.assertEqual(draft['facts_sha256'], hashlib.sha256(canonical.encode()).hexdigest())
        self.assertEqual(draft['status'], 'DRAFT')
        self.assertFalse(draft['ai_generated'])
        self.assertIsNone(draft['model'])
        self.assertTrue(draft['checks']['human_review_required'])
        self.assertEqual(draft['checks']['semantic_fact_check'], 'NOT_PERFORMED')
        self.assertIn('24.64℃', draft['text'])
        self.assertEqual(response.headers['cache-control'], 'no-store')
        paid.assert_not_called(); hf.assert_not_called()

    def test_template_default_and_repeat(self):
        one = self.client.post('/articles', json={}).json()
        two = self.client.post('/articles', json={}).json()
        self.assertEqual(one['article'], two['article'])
        self.assertEqual(one['facts_sha256'], two['facts_sha256'])

    def test_strict_and_redacted_invalid_requests(self):
        cases = [{'mode': 'bad'}, {'api_key': 'PRIVATE-KEY'}, {'csv': '/private/file'},
                 {'mode': 1}, {'max_tokens': True}, {'max_tokens': 127},
                 {'max_tokens': 4097}, {'timeout': 121}, {'timeout': 0},
                 {'timeout': '60'}, {'model': 'arbitrary'}, ['template']]
        for value in cases:
            with self.subTest(value=value), patch.object(app, 'create_draft') as generate:
                response = self.client.post('/articles', json=value)
                self.assertEqual(response.status_code, 422)
                self.assertNotIn('PRIVATE-KEY', response.text)
                self.assertNotIn('/private/file', response.text)
                generate.assert_not_called()
        self.assertEqual(self.client.post('/articles', content='{bad', headers={'Content-Type':'application/json'}).status_code, 422)

    def test_request_size_content_type_origin_and_host(self):
        self.assertEqual(self.client.post('/articles', content='{}').status_code, 415)
        self.assertEqual(self.client.post('/articles', content='x'*4097, headers={'Content-Type':'application/json'}).status_code, 413)
        self.assertEqual(self.client.post('/articles', json={}, headers={'Origin':'https://evil.example'}).status_code, 403)
        self.assertEqual(self.client.post('/articles', json={}, headers={'Origin':'http://testserver'}).status_code, 200)
        self.assertEqual(self.client.get('/health', headers={'Host':'evil.example'}).status_code, 400)

    def test_missing_key_and_hf_disabled_make_no_call(self):
        self.assertEqual(self.client.post('/articles', json={'mode':'openai'}).status_code, 503)
        with patch.object(ag, 'generate_huggingface') as hf:
            self.assertEqual(self.client.post('/articles', json={'mode':'huggingface'}).status_code, 503)
            hf.assert_not_called()
        self.assertEqual(self.client.post('/articles', json={}).status_code, 200)

    def test_mock_hf_opt_in_preserves_checks(self):
        os.environ['WEATHER_ENABLE_HF'] = '1'
        with patch.object(ag, 'generate_huggingface', return_value=ag.template_article(app.build_facts())) as hf:
            response = self.client.post('/articles', json={'mode':'huggingface'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['model_revision'], ag.HF_REVISION)
        self.assertTrue(response.json()['ai_generated'])
        hf.assert_called_once()

    def sdk(self, error=None, output=None, status='completed'):
        constructor = MagicMock()
        client = constructor.return_value.__enter__.return_value
        client.responses.create.side_effect = error
        client.responses.create.return_value.status = status
        client.responses.create.return_value.output_text = output if output is not None else json.dumps(ag.template_article(app.build_facts()), ensure_ascii=False)
        return constructor, client

    def test_mock_openai_through_local_api_contract(self):
        os.environ['OPENAI_API_KEY'] = 'test-only-placeholder'
        constructor, client = self.sdk()
        with patch('openai.OpenAI', constructor):
            response = self.client.post('/articles', json={'mode':'openai','max_tokens':800,'timeout':12})
        self.assertEqual(response.status_code, 200, response.text)
        draft = response.json()
        self.assertTrue(draft['ai_generated'])
        self.assertEqual(draft['checks']['numeric_whitelist'], 'passed')
        args = client.responses.create.call_args.kwargs
        self.assertEqual(args['reasoning'], {'effort':'none'})
        self.assertEqual(args['text']['format']['type'], 'json_schema')
        self.assertTrue(args['text']['format']['strict'])
        self.assertNotIn('temperature', args)
        self.assertFalse(args['store'])
        self.assertEqual(args['max_output_tokens'],800)
        self.assertNotIn('file_name', args['input'])
        self.assertNotIn('sha256', args['input'])
        self.assertNotIn('test-only-placeholder', response.text)
        constructor.assert_called_once_with(api_key='test-only-placeholder',base_url='https://api.openai.com/v1',timeout=12,max_retries=0)

    def test_provider_errors_redacted_and_recoverable(self):
        os.environ['OPENAI_API_KEY'] = 'test-only-placeholder'
        request = httpx.Request('POST','https://api.openai.com/v1/responses')
        cases=[(openai.AuthenticationError('PRIVATE-ERROR',response=httpx.Response(401,request=request),body=None),502),
               (openai.RateLimitError('PRIVATE-ERROR',response=httpx.Response(429,request=request),body=None),429),
               (openai.APITimeoutError(request=request),504),
               (RuntimeError('PRIVATE-ERROR'),502)]
        for error, code in cases:
            with self.subTest(code=code):
                constructor, client = self.sdk(error=error)
                with patch('openai.OpenAI',constructor):
                    response = self.client.post('/articles',json={'mode':'openai'})
                self.assertEqual(response.status_code,code,response.text)
                self.assertNotIn('PRIVATE-ERROR',response.text)
                client.responses.create.assert_called_once()
                self.assertEqual(self.client.post('/articles',json={}).status_code,200)

    def test_bad_model_output_never_becomes_template(self):
        os.environ['OPENAI_API_KEY'] = 'test-only-placeholder'
        cases=[('', 'completed'), ('not json', 'completed'), ('{}','completed'),
            (json.dumps({'title':'서울','lead':'서울','body':'999℃'}),'completed'),
            (json.dumps({'title':'부산','lead':'기온','body':'관측'}),'completed'),
            (None, 'incomplete')]
        for output,status in cases:
            with self.subTest(output=output,status=status):
                constructor,_ = self.sdk(output=output,status=status)
                with patch('openai.OpenAI',constructor):
                    response=self.client.post('/articles',json={'mode':'openai'})
                self.assertEqual(response.status_code,502,response.text)
                self.assertNotIn('article',response.json())

    def test_csv_errors_prevent_model_and_hide_paths(self):
        os.environ['WEATHER_CSV_PATH']='/private/missing.csv'
        with patch.object(app,'create_draft') as generate:
            response=self.client.post('/articles',json={'mode':'openai'})
        self.assertEqual(response.status_code,422)
        self.assertNotIn('/private',response.text)
        generate.assert_not_called()

    def test_csv_station_and_size_limits(self):
        os.environ['WEATHER_STATION']='159'
        self.assertEqual(self.client.get('/facts').status_code,422)
        os.environ.pop('WEATHER_STATION')
        with patch.object(app,'MAX_CSV_BYTES',1):
            self.assertEqual(self.client.get('/facts').status_code,422)

    def test_single_flight_lock_released(self):
        app.GENERATION_LOCK.acquire()
        try:
            self.assertEqual(self.client.post('/articles',json={}).status_code,429)
        finally:
            app.GENERATION_LOCK.release()
        self.assertEqual(self.client.post('/articles',json={}).status_code,200)

    def test_no_db_or_server_file_writes(self):
        with patch('pathlib.Path.write_text',side_effect=AssertionError('write forbidden')), patch('pathlib.Path.write_bytes',side_effect=AssertionError('write forbidden')):
            self.assertEqual(self.client.post('/articles',json={}).status_code,200)

    def test_custom_model_omits_incompatible_options(self):
        os.environ.update(OPENAI_API_KEY='test-only-placeholder',OPENAI_MODEL='custom-model')
        constructor,client=self.sdk()
        with patch('openai.OpenAI',constructor):
            self.assertEqual(self.client.post('/articles',json={'mode':'openai'}).status_code,200)
        self.assertNotIn('reasoning',client.responses.create.call_args.kwargs)
        self.assertNotIn('temperature',client.responses.create.call_args.kwargs)


class LauncherTests(unittest.TestCase):
    def test_getpass_no_echo_fallback(self):
        with patch('getpass.getpass',side_effect=start_api.getpass.GetPassWarning('unsafe')):
            with self.assertRaises(SystemExit):start_api.read_key()
        with patch('getpass.getpass',side_effect=EOFError):
            with self.assertRaises(SystemExit):start_api.read_key()

    def test_offline_clears_external_modes_and_binds_loopback(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test-only','WEATHER_ENABLE_HF':'1'},clear=True), patch.object(sys,'argv',['start_api.py','--offline']), patch('uvicorn.run') as run, patch.object(start_api,'read_key') as read:
            start_api.main()
            self.assertNotIn('OPENAI_API_KEY',os.environ)
            self.assertNotIn('WEATHER_ENABLE_HF',os.environ)
            read.assert_not_called()
            run.assert_called_once_with('app:app',host='127.0.0.1',port=8000,access_log=False)

    def test_session_key_never_written(self):
        with patch.dict(os.environ,{},clear=True), patch.object(sys,'argv',['start_api.py']), patch('uvicorn.run'), patch.object(start_api,'read_key',return_value='test-only'), patch('pathlib.Path.write_text',side_effect=AssertionError('key write')):
            start_api.main()
            self.assertEqual(os.environ['OPENAI_API_KEY'],'test-only')


if __name__=='__main__':unittest.main()
