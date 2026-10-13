"""본인 터미널에서 실행. 키는 비표시 입력으로 현재 서버 프로세스에만 전달합니다."""
import argparse
import getpass
import os
import warnings


def read_key():
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        try:
            return getpass.getpass('본인 OpenAI API 키 (화면 비표시, Enter=template): ').strip()
        except (getpass.GetPassWarning, EOFError):
            raise SystemExit('비표시 입력을 지원하는 VS Code 터미널에서 실행하세요.') from None


def main():
    parser = argparse.ArgumentParser(description='기상 기사 로컬 실습 서버')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--offline', action='store_true', help='키 입력 생략, OpenAI/Hugging Face 비활성')
    modes.add_argument('--enable-huggingface', action='store_true', help='수 GB 모델 다운로드/로컬 추론을 명시적으로 허용')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('--port는 1024~65535여야 합니다.')
    if args.offline:
        os.environ.pop('OPENAI_API_KEY', None)
        os.environ.pop('WEATHER_ENABLE_HF', None)
    elif not os.getenv('OPENAI_API_KEY', '').strip():
        key = read_key()
        if key:
            os.environ['OPENAI_API_KEY'] = key
    if args.enable_huggingface:
        os.environ['WEATHER_ENABLE_HF'] = '1'
    import uvicorn
    # 한 프로세스에서만 실행합니다. --reload/여러 worker/공개 배포 용도가 아닙니다.
    uvicorn.run('app:app', host='127.0.0.1', port=args.port, access_log=False)


if __name__ == '__main__':
    main()
