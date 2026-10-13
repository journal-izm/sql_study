"""오프라인 테스트. 아래 고정 수치는 검사용 가상 값이며 기사 근거가 아닙니다."""
import copy
import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import article_generation as ag


def facts_fixture():
    return {'station_id': 108, 'station_name': '서울',
        'metric': '일평균기온의 월 산술평균', 'unit': '℃',
        'baseline': {'year': 2024, 'month': 9, 'expected_days': 30, 'valid_days': 30, 'mean_daily_temperature_c': 20.0},
        'target': {'year': 2025, 'month': 9, 'expected_days': 30, 'valid_days': 30, 'mean_daily_temperature_c': 21.5},
        'difference_c': 1.5,
        'sources': [{'source_url': 'https://data.kma.go.kr/', 'file_name': 'private-name.csv', 'sha256': 'a'*64, 'batch_id': 99}],
        'limitations': ['두 기간으로 장기 추세나 원인을 단정하지 않음']}


class GenerationTests(unittest.TestCase):
    def test_template_default_and_provenance(self):
        draft = ag.create_draft(facts_fixture())
        self.assertEqual(draft['mode'], 'template')
        self.assertEqual(draft['status'], 'DRAFT')
        self.assertIsNone(draft['model'])
        self.assertEqual(len(draft['facts_sha256']), 64)
        self.assertIn('1.50℃ 높았다', draft['article']['lead'])
        self.assertEqual(draft['checks']['semantic_fact_check'], 'NOT_PERFORMED')
        self.assertTrue(draft['checks']['human_review_required'])

    def test_zero_negative_and_rounding(self):
        for diff, target, phrase in [(0, 20, '같았다'), (-1.5, 18.5, '1.50℃ 낮았다'), (1.49, 21.5, '1.49℃ 높았다')]:
            f = facts_fixture()
            f['difference_c'], f['target']['mean_daily_temperature_c'] = diff, target
            self.assertIn(phrase, ag.create_draft(f)['article']['lead'])

    def test_fact_checks(self):
        updates = [lambda f: f.pop('sources'), lambda f: f.update(unit='F'),
            lambda f: f['baseline'].update(valid_days=29), lambda f: f.update(difference_c=20),
            lambda f: f['baseline'].update(year=2025), lambda f: f['target'].update(month=8),
            lambda f: f['target'].update(mean_daily_temperature_c=float('nan')),
            lambda f: f.update(kind='unrecognized'), lambda f: f.update(limitations=[])]
        for update in updates:
            f = facts_fixture()
            update(f)
            with self.subTest(f=f), self.assertRaises(ValueError):
                ag.create_draft(f)

    def test_generation_limits(self):
        for kwargs in [{'max_tokens': 1}, {'max_tokens': True}, {'timeout': float('nan')}, {'timeout': 301}, {'mode': 'bad'}, {'model': 'x'}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                ag.create_draft(facts_fixture(), **kwargs)

    def test_api_projection_does_not_leak_file_or_database_ids(self):
        payload = json.dumps(ag.public_facts(facts_fixture()))
        for excluded in ['file_name', 'sha256', 'batch_id', 'station_id', 'private-name']:
            self.assertNotIn(excluded, payload)

    def test_json_contract(self):
        for value in ['', 'plain text', '[]', '{"title":"x"}', '```json\n{}\n```']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                ag._parse_model_json(value)

    def test_unsupported_numbers_and_ratios_stop(self):
        f = facts_fixture()
        for body in ['서울의 기온은999.0℃였다', '서울 기온 20% 상승', '서울 기온 20퍼센트 상승']:
            with self.subTest(body=body), self.assertRaisesRegex(ValueError, '숫자|비율'):
                ag.check_article({'title': '서울', 'lead': '기온 비교', 'body': body}, f, 'openai')

    def test_article_fields_and_station(self):
        for a in [{'title': '', 'lead': '서울', 'body': '본문'},
                  {'title': '다른 곳', 'lead': '비교', 'body': '본문'},
                  {'title': '서울'*101, 'lead': '비교', 'body': '본문'}]:
            with self.subTest(a=a), self.assertRaises(ValueError):
                ag.check_article(a, facts_fixture(), 'openai')

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_openai_key(self):
        with self.assertRaisesRegex(RuntimeError, 'OPENAI_API_KEY'):
            ag.create_draft(facts_fixture(), mode='openai')

    def mocked_openai(self, status='completed', output=None, error=None):
        fake_client = MagicMock()
        response = SimpleNamespace(status=status, output_text=output or json.dumps(
            {'title': '서울 기온 비교', 'lead': '서울의 기온을 비교했다.', 'body': '서울 기온은 21.5℃다. 원인을 단정하지 않는다.'}, ensure_ascii=False))
        fake_client.responses.create.return_value = response
        fake_client.responses.create.side_effect = error
        constructor = MagicMock()
        constructor.return_value.__enter__.return_value = fake_client
        return constructor, fake_client

    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-only-placeholder'}, clear=True)
    def test_openai_response_contract_and_audit(self):
        constructor, client = self.mocked_openai()
        with patch.dict(sys.modules, {'openai': SimpleNamespace(OpenAI=constructor)}):
            draft = ag.create_draft(facts_fixture(), mode='openai', timeout=12)
        self.assertEqual(draft['model'], ag.OPENAI_MODEL)
        constructor.assert_called_once_with(timeout=12, max_retries=0)
        kwargs = client.responses.create.call_args.kwargs
        self.assertFalse(kwargs['store'])
        self.assertEqual(kwargs['model'], ag.OPENAI_MODEL)
        self.assertEqual(kwargs['text'], {'format': {'type': 'json_object'}})
        self.assertNotIn('private-name', kwargs['input'])

    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-only-placeholder'}, clear=True)
    def test_incomplete_and_errors_do_not_become_template(self):
        for status, error in [('incomplete', None), ('completed', TimeoutError('secret material'))]:
            constructor, _ = self.mocked_openai(status=status, error=error)
            with patch.dict(sys.modules, {'openai': SimpleNamespace(OpenAI=constructor)}):
                with self.assertRaises(RuntimeError) as caught:
                    ag.create_draft(facts_fixture(), mode='openai')
                self.assertNotIn('secret material', str(caught.exception))

    @patch.dict(os.environ, {}, clear=True)
    def test_hf_contract_cpu_revision_no_remote_code(self):
        tokenizer = MagicMock()
        tokenizer.eos_token_id = 0
        inputs = MagicMock()
        inputs.__getitem__.return_value.shape = [1, 3]
        inputs.keys.return_value = ['input_ids']
        tokenizer.return_value.to.return_value = inputs
        tokenizer.decode.return_value = json.dumps({'title': '서울', 'lead': '서울 기온 비교', 'body': '서울 기온은 21.5℃다.'}, ensure_ascii=False)
        model = MagicMock()
        model.generate.return_value = [[4, 5, 6, 7, 8, 0]]
        torch = MagicMock()
        torch.cuda.is_available.return_value = False
        auto_tokenizer, auto_model = MagicMock(), MagicMock()
        auto_tokenizer.from_pretrained.return_value = tokenizer
        auto_model.from_pretrained.return_value = model
        with patch.dict(sys.modules, {'torch': torch, 'transformers': SimpleNamespace(
                AutoTokenizer=auto_tokenizer, AutoModelForCausalLM=auto_model)}):
            draft = ag.create_draft(facts_fixture(), mode='huggingface')
        kwargs = auto_model.from_pretrained.call_args.kwargs
        self.assertFalse(kwargs['trust_remote_code'])
        self.assertTrue(kwargs['use_safetensors'])
        self.assertEqual(kwargs['revision'], ag.HF_REVISION)
        self.assertEqual(kwargs['torch_dtype'], torch.float32)
        self.assertEqual(draft['model_revision'], ag.HF_REVISION)
        self.assertEqual(tokenizer.decode.call_args.args[0], [7, 8, 0])
        self.assertFalse(model.generate.call_args.kwargs['do_sample'])
        model.to.assert_called_once_with('cpu')


class FactSafetyTests(unittest.TestCase):
    def hourly_facts(self):
        from pathlib import Path
        from hourly_weather import read_hourly_csv,summarize_hourly
        path=Path(__file__).parent/'fixtures'/'asos_hourly_seoul_20260901_03.csv'
        rows,digest,_=read_hourly_csv(path)
        return summarize_hourly(rows,source_url='https://data.kma.go.kr/',file_name=path.name,sha256=digest)

    def test_impossible_coverage_dates_and_counts_rejected(self):
        changes=[lambda f:f['coverage'].update(complete_days=10000,used_hours=240000),
                 lambda f:f.update(period_end='2026-08-01'),lambda f:f.update(timezone='UTC'),
                 lambda f:f['coverage'].update(null_temperatures=-1),
                 lambda f:f['coverage'].update(total_rows=999),
                 lambda f:f['coverage'].update(complete_days=True),
                 lambda f:f['coverage'].update(excluded_days=0),
                 lambda f:f['coverage'].update(missing_timestamps=0),
                 lambda f:f['included_dates'].append('2026-09-02'),
                 lambda f:f['excluded_dates'][0].update(observed_hours=24),
                 lambda f:f.update(period_start='not-a-date')]
        for change in changes:
            facts=self.hourly_facts();change(facts)
            with self.subTest(change=change),patch.object(ag,'generate_openai') as generate:
                with self.assertRaises(ValueError):ag.create_draft(facts,mode='openai')
                generate.assert_not_called()

    def test_nested_private_fields_never_projected(self):
        monthly=facts_fixture()
        monthly['baseline']['file_name']='private-baseline.csv'
        monthly['target']['sha256']='private-target-hash'
        hourly=self.hourly_facts()
        hourly['coverage']['file_name']='private-hourly.csv'
        for facts in (monthly,hourly):
            ag.validate_facts(facts)
            projected=json.dumps(ag.public_facts(facts))
            self.assertNotIn('private-',projected)
            self.assertNotIn('file_name',projected)
            self.assertNotIn('sha256',projected)

    def test_nonstring_limitations_rejected_before_model(self):
        facts=facts_fixture();facts['limitations']=[{'file_name':'private.csv'}]
        with patch.object(ag,'generate_openai') as generate,self.assertRaises(ValueError):
            ag.create_draft(facts,mode='openai')
        generate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
