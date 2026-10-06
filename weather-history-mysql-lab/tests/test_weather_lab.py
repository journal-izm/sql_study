"""검증용 임시 가상 데이터이며 기사 근거로 제공하는 데이터가 아닙니다."""
import tempfile
import unittest
from pathlib import Path
from datetime import date
from decimal import Decimal
from weather_lab import read_csv, summarize

class WeatherTests(unittest.TestCase):
    def parse(self,text,encoding='utf-8-sig'):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fixture.csv'
            p.write_bytes(text.encode(encoding))
            return read_csv(p)[0]

    # 테스트 이름이 나타내는 정상/오류 상황을 임시 데이터로 재현합니다. 실물 관측 자료를 만들지 않습니다.
    def test_kma_cp949_and_null(self):
        rows=self.parse('지점,지점명,일시,평균기온(℃)\n108,서울,2025-09-01,0\n108,서울,2025-09-02,\n','cp949')
        self.assertEqual(rows[0][3],Decimal('0'))
        self.assertIsNone(rows[1][3])

    # 테스트 이름이 나타내는 정상/오류 상황을 임시 데이터로 재현합니다. 실물 관측 자료를 만들지 않습니다.
    def test_duplicate(self):
        with self.assertRaisesRegex(ValueError,'중복'):
            self.parse('지점,지점명,일시,평균기온(℃)\n108,서울,2025-09-01,20\n108,서울,2025-09-01,20\n')

    # 테스트 이름이 나타내는 정상/오류 상황을 임시 데이터로 재현합니다. 실물 관측 자료를 만들지 않습니다.
    def test_bad_temperature(self):
        for v in ['NaN','-999','20.123']:
            with self.subTest(v=v), self.assertRaises(ValueError):
                self.parse(f'지점,지점명,일시,평균기온(℃)\n108,서울,2025-09-01,{v}\n')

    # 테스트 이름이 나타내는 정상/오류 상황을 임시 데이터로 재현합니다. 실물 관측 자료를 만들지 않습니다.
    def test_hourly_rejected(self):
        with self.assertRaises(ValueError):
            self.parse('지점,지점명,일시,평균기온(℃)\n108,서울,2025-09-01 01:00,20\n')

    # 테스트 이름이 나타내는 정상/오류 상황을 임시 데이터로 재현합니다. 실물 관측 자료를 만들지 않습니다.
    def test_missing_column(self):
        with self.assertRaisesRegex(ValueError,'필수 열'):
            self.parse('지점,일시\n108,2025-09-01\n')

    # 테스트 이름이 나타내는 정상/오류 상황을 임시 데이터로 재현합니다. 실물 관측 자료를 만들지 않습니다.
    def test_complete_month(self):
        rows=[{'observed_date':date(2025,9,d),'avg_temp_c':Decimal(d)} for d in range(1,31)]
        summary,mean=summarize(rows,2025,9)
        self.assertEqual(mean,Decimal('15.5'))
        self.assertEqual(summary['valid_days'],30)

    # 테스트 이름이 나타내는 정상/오류 상황을 임시 데이터로 재현합니다. 실물 관측 자료를 만들지 않습니다.
    def test_missing_and_null_stop(self):
        rows=[{'observed_date':date(2025,9,d),'avg_temp_c':Decimal('20')} for d in range(1,30)]
        rows[0]['avg_temp_c']=None
        with self.assertRaisesRegex(ValueError,'누락 날짜'):
            summarize(rows,2025,9)

if __name__=='__main__': unittest.main()
