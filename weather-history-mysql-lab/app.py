"""로컬 수업용 FastAPI. CSV 집계/기사 검사는 기존 모듈을 그대로 사용합니다."""
import os
from pathlib import Path
from threading import Lock
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from article_generation import (GenerationError, OPENAI_MODEL, HF_MODEL,
                                create_draft, render_draft)
from hourly_weather import read_hourly_csv, summarize_hourly

BASE = Path(__file__).resolve().parent
SAMPLE = BASE / 'tests/fixtures/asos_hourly_seoul_20260901_03.csv'
MAX_REQUEST_BYTES = 4096
MAX_CSV_BYTES = 10 * 1024 * 1024
GENERATION_LOCK = Lock()
app = FastAPI(title='기상 관측 데이터 기사 실습', version='2.0.0',
    description='실제 ASOS CSV → Python 집계 → DRAFT. template는 AI 미호출 사전 점검입니다. '
                'OpenAI는 유료이며 Hugging Face는 명시적으로 활성화해야 합니다. DB 자동 저장 없음.')
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]', 'testserver'])


class ArticleRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    mode: Literal['template', 'huggingface', 'openai'] = 'template'
    max_tokens: int = Field(default=900, ge=128, le=4096)
    timeout: float = Field(default=60, ge=1, le=120, allow_inf_nan=False)


@app.middleware('http')
async def local_request_guard(request: Request, call_next):
    # CORS 허용 없이 동일 출처 브라우저만 사용. DNS rebinding은 TrustedHost로 차단합니다.
    if request.method == 'POST':
        origin = request.headers.get('origin')
        expected = f'{request.url.scheme}://{request.url.netloc}'
        if origin and origin != expected:
            return JSONResponse({'detail': '같은 로컬 화면에서 요청하세요.'}, status_code=403)
        if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
            return JSONResponse({'detail': 'application/json 요청만 지원합니다.'}, status_code=415)
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_REQUEST_BYTES:
                return JSONResponse({'detail': '요청 크기 제한은 4096바이트입니다.'}, status_code=413)
            chunks.append(chunk)
        request._body = b''.join(chunks)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    return response


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    # 기본 오류의 input 필드는 실수로 보낸 키/파일 경로를 그대로 반사할 수 있습니다.
    return JSONResponse({'detail': '요청 형식을 확인하세요. mode, max_tokens(128~4096), timeout(1~120)만 허용합니다.'}, status_code=422)


def build_facts():
    configured = os.getenv('WEATHER_CSV_PATH', '').strip()
    path = Path(configured) if configured else SAMPLE
    if not path.is_absolute():
        path = BASE / path
    if path.stat().st_size > MAX_CSV_BYTES:
        raise ValueError('CSV size limit')
    rows, digest, _ = read_hourly_csv(path)
    if len(rows) > 100000:
        raise ValueError('CSV row limit')
    selected = os.getenv('WEATHER_STATION', '').strip()
    return summarize_hourly(rows, source_url='https://data.kma.go.kr/',
        file_name=path.name, sha256=digest, station=int(selected) if selected else None)


def checked_facts():
    try:
        return build_facts()
    except (OSError, ValueError, OverflowError):
        raise HTTPException(422, 'CSV 검증 실패: 파일·필수 열·중복·완전한 날짜·관측소 선택을 확인하세요.') from None


@app.get('/', include_in_schema=False)
def home():
    return FileResponse(BASE / 'index.html')


@app.get('/health')
def health():
    return {'status': 'ok', 'live_api_verified': False,
        'dataset': 'configured_csv' if os.getenv('WEATHER_CSV_PATH', '').strip() else 'bundled_48_rows',
        'openai_configured': bool(os.getenv('OPENAI_API_KEY', '').strip()),
        'huggingface_enabled': os.getenv('WEATHER_ENABLE_HF') == '1',
        'openai_model': os.getenv('OPENAI_MODEL', '').strip() or OPENAI_MODEL,
        'huggingface_model': os.getenv('HF_MODEL', '').strip() or HF_MODEL}


@app.get('/facts', summary='모델 호출 없이 CSV 집계 확인')
def facts():
    return checked_facts()


@app.post('/articles', summary='검증 근거로 기사 초안 만들기')
def articles(request: ArticleRequest):
    if not GENERATION_LOCK.acquire(blocking=False):
        raise HTTPException(429, '이미 생성 중입니다. 결과를 기다리세요. 자동 재시도하지 않습니다.')
    try:
        facts = checked_facts()
        if request.mode == 'huggingface' and os.getenv('WEATHER_ENABLE_HF') != '1':
            raise HTTPException(503, 'Hugging Face는 기본 비활성입니다. 설치 후 start_api.py --enable-huggingface로 실행하세요.')
        try:
            draft = create_draft(facts, request.mode, max_tokens=request.max_tokens, timeout=request.timeout)
        except GenerationError as exc:
            raise HTTPException(exc.status, str(exc)) from None
        except ValueError:
            raise HTTPException(502, '기사 검증 실패: 형식·관측소·근거 밖 숫자 등을 확인하세요. 초안을 저장하지 않습니다.') from None
        except Exception:
            raise HTTPException(502, '생성 실패: 선택한 모드의 설치·모델·메모리·접근 권한을 확인하세요. 원본 오류는 노출하지 않습니다.') from None
        return {**draft, 'ai_generated': request.mode != 'template', 'text': render_draft(draft)}
    finally:
        GENERATION_LOCK.release()
