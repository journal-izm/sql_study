"""에러 케이스는 가상 값입니다. fixtures의 ASOS 발췌만 사용자 제공 실제 관측입니다."""
import tempfile
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from article_generation import create_draft
from hourly_weather import read_hourly_csv, summarize_hourly


class HourlyTests(unittest.TestCase):
    def rows(self, n=48):
        start = datetime(2025, 9, 1)
        return [{'station_id': 108, 'station_name': '서울', 'observed_at': start + timedelta(hours=h),
                 'temperature_c': Decimal('20'), 'quality_flag': ''} for h in range(n)]

    def summarize(self, rows):
        return summarize_hourly(rows, source_url='https://data.kma.go.kr/', file_name='test-only.csv', sha256='a'*64)

    def parse(self, text, encoding='utf-8-sig'):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'test.csv'
            p.write_bytes(text.encode(encoding))
            return read_hourly_csv(p)

    def test_complete_days(self):
        result=self.summarize(self.rows())
        self.assertEqual(result['coverage']['complete_days'], 2)
        self.assertEqual(result['coverage']['used_hours'], 48)
        self.assertEqual(result['mean_hourly_temperature_c'], 20.0)
        self.assertEqual(result['timezone'], 'Asia/Seoul')
        self.assertEqual(create_draft(result)['status'], 'DRAFT')

    def test_incomplete_endpoints_excluded(self):
        result=self.summarize(self.rows(73)[1:])
        self.assertEqual(result['coverage']['complete_days'], 2)
        self.assertEqual(result['coverage']['excluded_days'], 2)
        self.assertEqual(result['excluded_dates'][0]['observed_hours'], 23)
        self.assertEqual(result['excluded_dates'][-1]['observed_hours'], 1)
        self.assertEqual(result['coverage']['missing_timestamps'], 24)

    def test_missing_entire_day_is_visible(self):
        rows=self.rows(72)
        result=self.summarize(rows[:24]+rows[48:])
        self.assertEqual(result['coverage']['excluded_days'], 1)
        self.assertEqual(result['excluded_dates'][0]['missing_timestamps'], 24)

    def test_null_and_flags_exclude_entire_day(self):
        for key, value, field in [('temperature_c', None, 'null_temperatures'), ('quality_flag', '9', 'flagged_temperatures')]:
            rows=self.rows()
            rows[0][key]=value
            result=self.summarize(rows)
            self.assertEqual(result['coverage']['complete_days'], 1)
            self.assertEqual(result['coverage'][field], 1)

    def test_no_complete_day(self):
        with self.assertRaisesRegex(ValueError, '완전한 날짜'):
            self.summarize(self.rows(23))

    def test_duplicate_parser(self):
        with self.assertRaisesRegex(ValueError, '중복'):
            self.parse('지점,지점명,일시,기온(°C)\n108,서울,2025-09-01 00:00,20\n108,서울,2025-09-01 00:00,20')

    def test_cp949_zero_and_null(self):
        rows, _, encoding=self.parse('지점,지점명,일시,기온(°C)\n108,서울,2025-09-01 00:00,0\n108,서울,2025-09-01 01:00,', 'cp949')
        self.assertEqual(encoding, 'cp949')
        self.assertEqual(rows[0]['temperature_c'], Decimal(0))
        self.assertIsNone(rows[1]['temperature_c'])

    def test_bad_shape_date_temperature_headers(self):
        cases=[('2025-09-01', '20'), ('2025-09-01 00:30', '20'), ('2025-09-01 00:00', 'NaN'),
               ('2025-09-01 00:00', '-999'), ('2025-09-01 00:00', '20.123')]
        for stamp, temp in cases:
            with self.subTest(stamp=stamp,temp=temp), self.assertRaises(ValueError):
                self.parse(f'지점,지점명,일시,기온(°C)\n108,서울,{stamp},{temp}')
        with self.assertRaises(ValueError):
            self.parse('지점,지점명,일시,평균기온(℃)\n108,서울,2025-09-01,20')
        with self.assertRaises(ValueError):
            self.parse('지점,지점명,일시,기온(°C)\n108,서울,2025-09-01 00:00,20,extra')

    def test_multi_station_requires_selection(self):
        rows=self.rows()
        rows += [dict(r,station_id=159,station_name='부산') for r in self.rows()]
        with self.assertRaisesRegex(ValueError, '여러 관측소'):
            self.summarize(rows)

    def test_real_asos_excerpt(self):
        p=Path(__file__).parent/'fixtures'/'asos_hourly_seoul_20260901_03.csv'
        rows, digest, _=read_hourly_csv(p)
        result=summarize_hourly(rows,source_url='https://data.kma.go.kr/',file_name=p.name,sha256=digest)
        self.assertEqual(len(rows),48)
        self.assertEqual(result['coverage']['complete_days'],1)
        self.assertEqual(result['included_dates'],['2026-09-02'])
        self.assertEqual(result['mean_hourly_temperature_c'],24.64)
        self.assertEqual(result['coverage']['excluded_days'],2)


if __name__ == '__main__':
    unittest.main()
