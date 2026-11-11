import math
import os
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)

KST = timezone(timedelta(hours=9))
API_URL = "https://apihub.kma.go.kr/api/typ01/url/kma_sfctm2.php"

STATIONS = {
    "108": "서울",
    "159": "부산",
    "143": "대구",
    "112": "인천",
    "156": "광주",
    "133": "대전",
    "152": "울산",
    "184": "제주",
}

APP_VERSION = os.getenv("APP_VERSION", "v1")


def parse_number(raw, allow_negative=False):
    """결측값을 None으로 처리한다. 음수 기온은 유지한다."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(value):
        return None

    # 기온의 -99, -99.9 등 결측 표기를 처리한다.
    if value <= -90:
        return None

    # 습도·풍속·강수량의 음수 표기는 측정값으로 표시하지 않는다.
    if not allow_negative and value < 0:
        return None

    return value


def parse_observation(text, station, requested_tm):
    """
    ASOS 시간자료의 앞부분 필드 순서:
    TM STN WD WS GST_WD GST_WS GST_TM PA PS PT PR
    TA TD HM PV RN RN_DAY ...
    """
    for line in text.splitlines():
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        fields = line.split()

        if len(fields) < 17:
            continue

        if fields[0] != requested_tm or fields[1] != station:
            continue

        observed_at = datetime.strptime(fields[0], "%Y%m%d%H%M")

        return {
            "station": STATIONS[station],
            "station_id": station,
            "observed_at": observed_at.strftime("%Y-%m-%d %H:%M"),
            "temperature": parse_number(fields[11], allow_negative=True),
            "humidity": parse_number(fields[13]),
            "wind_speed": parse_number(fields[3]),
            "daily_rainfall": parse_number(fields[16]),
        }

    return None


@app.get("/")
def index():
    # 자료 수신 지연을 고려해 한 시간 전 정시를 기본으로 제시한다.
    default_time = (
        datetime.now(KST) - timedelta(hours=1)
    ).replace(minute=0, second=0, microsecond=0)

    return render_template(
        "index.html",
        stations=STATIONS,
        default_time=default_time.strftime("%Y-%m-%dT%H:%M"),
    )


@app.get("/healthz")
def health():
    # 외부 API 장애와 앱 자체의 실행 상태를 구분한다.
    return jsonify(status="ok")


@app.get("/api/weather")
def weather():
    station = request.args.get("station", "108")
    time_input = request.args.get("time", "")

    if station not in STATIONS:
        return jsonify(error="지원하지 않는 관측 지점입니다."), 400

    try:
        selected = datetime.strptime(
            time_input, "%Y-%m-%dT%H:%M"
        ).replace(tzinfo=KST)
    except ValueError:
        return jsonify(error="날짜와 시간을 올바르게 선택해 주세요."), 400

    if selected.minute != 0:
        return jsonify(error="시간자료는 정시로 선택해 주세요. 예: 14:00"), 400

    if selected > datetime.now(KST):
        return jsonify(error="미래의 관측자료는 조회할 수 없습니다."), 400

    api_key = os.getenv("KMA_API_KEY", "").strip()

    if not api_key or api_key.startswith("여기에"):
        return jsonify(
            error=".env에 기상청 API허브 인증키를 넣고 앱을 재시작해 주세요."
        ), 503

    requested_tm = selected.strftime("%Y%m%d%H%M")

    try:
        response = requests.get(
            API_URL,
            params={
                "tm": requested_tm,
                "stn": station,
                "help": "0",
                "authKey": api_key,
            },
            timeout=(5, 20),
        )
        response.raise_for_status()

    except requests.Timeout:
        return jsonify(
            error="기상청 응답 시간이 초과됐습니다. 잠시 후 다시 조회해 주세요."
        ), 504

    except requests.RequestException:
        # 예외 문자열에는 인증키가 포함된 요청 URL이 들어갈 수 있어
        # 그대로 브라우저나 로그에 출력하지 않는다.
        return jsonify(
            error="기상청 API 요청에 실패했습니다. 네트워크와 API 이용 상태를 확인해 주세요."
        ), 502

    observation = parse_observation(
        response.text, station, requested_tm
    )

    if observation is None:
        return jsonify(
            error=(
                "해당 시각의 관측자료를 읽지 못했습니다. "
                "조금 이전 시각으로 조회하거나 API허브의 인증키·활용승인 상태를 확인해 주세요."
            )
        ), 502

    return jsonify(
        **observation,
        version=APP_VERSION,
        server=socket.gethostname(),
        fetched_at=datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
    )


if __name__ == "__main__":
    # 로컬 학습용 서버. 0.0.0.0은 이후 Docker 실행도 고려한 설정이다.
    app.run(host="0.0.0.0", port=8000, debug=False)
    