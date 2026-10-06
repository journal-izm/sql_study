import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

import httpx
import pymysql
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")

CITIES = {
    "seoul": ("Seoul,KR", "서울"),
    "busan": ("Busan,KR", "부산"),
    "jeju": ("Jeju,KR", "제주"),
    "gwangju": ("Gwangju,KR", "광주"),
}


def db_error(exc):
    code = exc.args[0] if isinstance(exc, pymysql.MySQLError) and exc.args else None
    if code in (1062, 1451, 1452):
        return HTTPException(409, detail="중복 관측값 또는 외래키 연결을 확인하세요.")
    if code in (1048, 1406, 3819, 1265, 1366):
        return HTTPException(400, detail="필수값, 길이 또는 CHECK 조건을 확인하세요.")
    return HTTPException(500, detail="데이터베이스 작업 실패")


def get_db():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "weatherNewsDB"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=10.0) as client:
        app.state.http = client
        yield


app = FastAPI(title="OpenWeather + FastAPI + MySQL CRUD", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE / "public"), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(BASE / "public" / "index.html")


class ArticleCreate(BaseModel):
    weatherId: int | None = Field(default=None, gt=0)
    sourceRegion: str | None = None
    title: str
    leadText: str | None = None
    bodyText: str | None = None
    status: Literal["DRAFT", "REVIEW", "APPROVED", "REJECTED"] = "DRAFT"


# 기본값을 두지 않아 nullable 항목도 PUT 요청에서 반드시 명시하도록 합니다.
class ArticleReplace(BaseModel):
    weatherId: int | None = Field(..., gt=0)
    sourceRegion: str | None = Field(..., max_length=30)
    title: str = Field(..., min_length=1, max_length=200)
    leadText: str | None
    bodyText: str | None
    status: Literal["DRAFT", "REVIEW", "APPROVED", "REJECTED"]

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value):
        if not value.strip():
            raise ValueError("title은 공백만 입력할 수 없습니다.")
        return value


class ArticleUpdate(BaseModel):
    weatherId: int | None = Field(default=None, gt=0)
    sourceRegion: str | None = None
    title: str | None = None
    leadText: str | None = None
    bodyText: str | None = None
    status: Literal["DRAFT", "REVIEW", "APPROVED", "REJECTED"] | None = None


async def fetch_weather(city: str) -> dict:
    api_key = os.getenv("OPENWEATHER_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(503, detail="OPENWEATHER_API_KEY를 설정하세요.")

    query, korean_name = CITIES[city]
    try:
        response = await app.state.http.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": query, "appid": api_key, "units": "metric", "lang": "kr"},
        )
    except httpx.RequestError as exc:
        raise HTTPException(502, detail="OpenWeather 연결 실패") from exc

    if response.status_code != 200:
        raise HTTPException(502, detail=f"OpenWeather 오류 HTTP {response.status_code}")

    data = response.json()
    return {
        "city_code": city,
        "region_name": korean_name,
        "city_name": data["name"],
        "temperature": data["main"]["temp"],
        "feels_like": data["main"]["feels_like"],
        "humidity": data["main"]["humidity"],
        "wind_speed": data["wind"]["speed"],
        "description": data["weather"][0]["description"],
        "observed_at": datetime.fromtimestamp(data["dt"]),
    }


@app.get("/api/health")
def health():
    conn = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            row = cur.fetchone()
        return {"success": True, "mysql": row["ok"] == 1}
    except Exception as exc:
        raise HTTPException(503, detail=f"MySQL 연결 실패: {exc}")
    finally:
        if conn:
            conn.close()


@app.get("/api/weather")
async def weather(city: str = Query("seoul", pattern="^(seoul|busan|jeju|gwangju)$")):
    return {"success": True, "data": await fetch_weather(city)}


@app.post("/api/weather/collect")
async def collect_weather(city: str = Query("seoul", pattern="^(seoul|busan|jeju|gwangju)$")):
    item = await fetch_weather(city)
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO weather_observation
                (city_code, region_name, city_name, temperature, feels_like,
                 humidity, wind_speed, description, observed_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    item["city_code"], item["region_name"], item["city_name"],
                    item["temperature"], item["feels_like"], item["humidity"],
                    item["wind_speed"], item["description"], item["observed_at"]
                )
            )
            weather_id = cur.lastrowid
        conn.commit()
        return {"success": True, "weatherId": weather_id, "data": item}
    except Exception as exc:
        conn.rollback()
        raise db_error(exc) from exc
    finally:
        conn.close()


@app.get("/api/analysis/summary")
def summary():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT region_name,
                          COUNT(*) AS observation_count,
                          ROUND(AVG(temperature),1) AS avg_temperature,
                          MAX(temperature) AS max_temperature,
                          MIN(temperature) AS min_temperature,
                          ROUND(AVG(humidity),1) AS avg_humidity,
                          MAX(wind_speed) AS max_wind_speed
                   FROM weather_observation
                   GROUP BY region_name
                   ORDER BY avg_temperature DESC"""
            )
            rows = cur.fetchall()
        return {"success": True, "count": len(rows), "data": rows}
    finally:
        conn.close()


@app.post("/api/articles")
def create_article(payload: ArticleCreate):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO news_article
                (source_region,title,lead_text,body_text,status,weather_id)
                VALUES (%s,%s,%s,%s,%s,%s)""",
                (
                    payload.sourceRegion, payload.title, payload.leadText,
                    payload.bodyText, payload.status, payload.weatherId
                )
            )
            article_id = cur.lastrowid
            cur.execute("SELECT * FROM news_article WHERE article_id=%s", (article_id,))
            row = cur.fetchone()
        conn.commit()
        return {"success": True, "crud": "CREATE", "data": row}
    except Exception as exc:
        conn.rollback()
        raise db_error(exc) from exc
    finally:
        conn.close()


@app.get("/api/articles")
def read_articles():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM news_article ORDER BY article_id DESC")
            rows = cur.fetchall()
        return {"success": True, "crud": "READ", "count": len(rows), "data": rows}
    finally:
        conn.close()


@app.get("/api/articles/{article_id}")
def read_article(article_id: int):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM news_article WHERE article_id=%s", (article_id,))
            row = cur.fetchone()
        if not row:
            raise HTTPException(404, detail="기사를 찾을 수 없습니다.")
        return {"success": True, "crud": "READ", "data": row}
    finally:
        conn.close()


@app.put("/api/articles/{article_id}", summary="기사 전체 교체 (PUT)")
def replace_article(article_id: int, payload: ArticleReplace):
    """수정 가능한 6개 필드를 모두 전달합니다. 비어 있는 선택 필드는 null입니다."""
    if article_id <= 0:
        raise HTTPException(400, detail="id는 양의 정수입니다.")
    conn = get_db()
    try:
        with conn.cursor() as cur:
            # rowcount는 변경량이므로 동일 PUT 재요청 시 존재 여부 판단에 쓰지 않습니다.
            cur.execute("SELECT article_id FROM news_article WHERE article_id=%s FOR UPDATE", (article_id,))
            if not cur.fetchone():
                raise HTTPException(404, detail="기사를 찾을 수 없습니다.")
            cur.execute(
                """UPDATE news_article SET source_region=%s,title=%s,lead_text=%s,
                body_text=%s,status=%s,weather_id=%s WHERE article_id=%s""",
                (payload.sourceRegion, payload.title, payload.leadText,
                 payload.bodyText, payload.status, payload.weatherId, article_id)
            )
            cur.execute("SELECT * FROM news_article WHERE article_id=%s", (article_id,))
            row = cur.fetchone()
        conn.commit()
        return {"success": True, "crud": "UPDATE", "method": "PUT", "data": row}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise db_error(exc) from exc
    finally:
        conn.close()


@app.patch("/api/articles/{article_id}", summary="기사 부분 수정 (PATCH)")
def update_article(article_id: int, payload: ArticleUpdate):
    raw = payload.model_dump(exclude_unset=True)
    if raw.get("title", "valid") is None or raw.get("status", "DRAFT") is None:
        raise HTTPException(400, detail="title과 status는 null로 변경할 수 없습니다.")
    mapping = {
        "weatherId": "weather_id",
        "sourceRegion": "source_region",
        "title": "title",
        "leadText": "lead_text",
        "bodyText": "body_text",
        "status": "status",
    }
    if not raw:
        raise HTTPException(400, detail="수정할 값을 입력하세요.")

    set_parts = []
    values = []
    for key, value in raw.items():
        set_parts.append(f"{mapping[key]}=%s")
        values.append(value)
    values.append(article_id)

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE news_article SET {', '.join(set_parts)} WHERE article_id=%s",
                tuple(values)
            )
            cur.execute("SELECT * FROM news_article WHERE article_id=%s", (article_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, detail="기사를 찾을 수 없습니다.")
        conn.commit()
        return {"success": True, "crud": "UPDATE", "data": row}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise db_error(exc) from exc
    finally:
        conn.close()


@app.delete("/api/articles/{article_id}")
def delete_article(article_id: int):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM news_article WHERE article_id=%s", (article_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, detail="기사를 찾을 수 없습니다.")
            cur.execute("DELETE FROM news_article WHERE article_id=%s", (article_id,))
        conn.commit()
        return {"success": True, "crud": "DELETE", "deleted": row}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()

