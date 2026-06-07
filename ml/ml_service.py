import httpx
import math
from datetime import datetime, timedelta
from typing import Optional
from ml.comfort_model import predict_comfort
import os

# 환경변수에서 기상청 API 키 로드
# 실행 전 터미널에서: export KMA_API_KEY="발급받은키"
KMA_API_KEY = os.getenv("KMA_API_KEY", "")

# 기상청 단기예보 API URL
KMA_BASE_URL = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"


# ── 기상청 격자 좌표 변환 (위도/경도 → nx, ny) ──────────────────
def latlon_to_grid(lat: float, lon: float) -> tuple[int, int]:
    """
    기상청은 GPS 좌표를 직접 못 받고 자체 격자계(nx, ny)를 사용.
    공식 변환 공식 적용.
    """
    RE = 6371.00877
    GRID = 5.0
    SLAT1 = 30.0
    SLAT2 = 60.0
    OLON = 126.0
    OLAT = 38.0
    XO = 43
    YO = 136

    DEGRAD = math.pi / 180.0
    re = RE / GRID
    slat1 = SLAT1 * DEGRAD
    slat2 = SLAT2 * DEGRAD
    olon = OLON * DEGRAD
    olat = OLAT * DEGRAD

    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = (sf ** sn) * math.cos(slat1) / sn
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re * sf / (ro ** sn)

    ra = math.tan(math.pi * 0.25 + lat * DEGRAD * 0.5)
    ra = re * sf / (ra ** sn)
    theta = lon * DEGRAD - olon
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn

    nx = int(ra * math.sin(theta) + XO + 0.5)
    ny = int(ro - ra * math.cos(theta) + YO + 0.5)
    return nx, ny


def _get_base_time() -> tuple[str, str]:
    """
    기상청 초단기실황은 매 정시 발표, 10분 딜레이 존재.
    현재 시각 기준으로 가장 최근 발표 시각 계산.
    """
    now = datetime.now()
    # 10분 딜레이 감안해서 현재 시각 - 1시간 사용
    base_dt = now - timedelta(hours=1)
    base_date = base_dt.strftime("%Y%m%d")
    base_time = base_dt.strftime("%H00")
    return base_date, base_time


async def _fetch_kma_api(lat: float, lng: float) -> Optional[dict]:
    """기상청 초단기실황 API 실제 호출"""
    nx, ny = latlon_to_grid(lat, lng)
    base_date, base_time = _get_base_time()

    params = {
        "ServiceKey": KMA_API_KEY,
        "pageNo": "1",
        "numOfRows": "1000",
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": str(nx),
        "ny": str(ny),
    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        res = await client.get(KMA_BASE_URL, params=params)
        res.raise_for_status()
        data = res.json()

    items = data["response"]["body"]["items"]["item"]

    # category 코드별 값 추출
    # T1H = 기온, RN1 = 강수량, WSD = 풍속
    result = {}
    for item in items:
        result[item["category"]] = item["obsrValue"]

    temperature = float(result.get("T1H", 20))

    # 기상청 단기예보에는 자외선 지수가 없음 → 시간/계절 기반 추정
    now = datetime.now()
    uv_index = _estimate_uv(now.month, now.hour)

    return {
        "temperature": temperature,
        "uv_index": uv_index,
        "month": now.month,
        "hour": now.hour,
        "source": "kma",
        "nx": nx,
        "ny": ny,
    }


def _estimate_uv(month: int, hour: int) -> float:
    """
    기상청 단기예보에 자외선 지수가 없으므로
    월/시간 기반으로 추정 (생활기상정보 API 별도 연동 가능)
    """
    if hour < 7 or hour > 19:
        return 0.0
    # 시간대별 기본 UV (정오 최대)
    hour_factor = 1.0 - abs(hour - 13) / 7.0
    hour_factor = max(0.0, hour_factor)
    # 계절별 최대 UV
    if month in [6, 7, 8]:
        max_uv = 10.0
    elif month in [4, 5, 9]:
        max_uv = 7.0
    elif month in [3, 10]:
        max_uv = 5.0
    else:
        max_uv = 2.0
    return round(max_uv * hour_factor, 1)


def _mock_weather(lat: float, lng: float) -> dict:
    """API 키 없을 때 계절/시간 기반 mock 데이터"""
    now = datetime.now()
    month, hour = now.month, now.hour

    if month in [6, 7, 8]:
        temp = 30 + (1 if 11 <= hour <= 15 else -3)
    elif month in [12, 1, 2]:
        temp = 3 + (3 if 11 <= hour <= 14 else 0)
    elif month in [3, 4, 5]:
        temp = 18 + (2 if 11 <= hour <= 14 else 0)
    else:
        temp = 16 + (2 if 11 <= hour <= 14 else 0)

    return {
        "temperature": temp,
        "uv_index": _estimate_uv(month, hour),
        "month": month,
        "hour": hour,
        "source": "mock (KMA_API_KEY 없음)",
    }


async def get_weather_data(lat: float, lng: float) -> dict:
    """
    기상청 API 키 있으면 실제 호출, 없으면 mock 반환.
    API 호출 실패 시에도 mock으로 fallback.
    """
    if not KMA_API_KEY:
        return _mock_weather(lat, lng)
    try:
        return await _fetch_kma_api(lat, lng)
    except Exception as e:
        print(f"⚠️ 기상청 API 오류 ({e}), mock 데이터 사용")
        return _mock_weather(lat, lng)


# ── 거리 / 스코어링 (기존과 동일) ──────────────────────────────

def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 간 거리(미터) 계산 - Haversine 공식"""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def score_rest_areas(rest_areas: list, weather: dict) -> list:
    """각 휴식처에 ML 쾌적도 점수 부여 후 정렬"""
    scored = []
    for area in rest_areas:
        comfort = predict_comfort(
            month=weather["month"],
            hour=weather["hour"],
            temperature=weather["temperature"],
            uv_index=weather["uv_index"],
            has_shade=area.has_shade_structure
        )
        scored.append({
            "area": area,
            "comfort_score": comfort,
            "distance_m": area._distance
        })
    scored.sort(key=lambda x: (-x["comfort_score"], x["distance_m"]))
    return scored


def get_comfort_message(score: float, has_shade: bool) -> str:
    """쾌적도 점수에 따른 메시지 생성"""
    if score >= 80:
        shade_emoji = "🌳" if has_shade else "😎"
        return f"{shade_emoji} 완벽한 휴식처! 그늘 확률 {min(95, int(score))}%! 대피하세요!"
    elif score >= 60:
        return f"🌤️ 괜찮은 자리예요. 쾌적도 {int(score)}점"
    elif score >= 40:
        return f"😅 좀 덥긴 한데... 그나마 나은 자리 ({int(score)}점)"
    else:
        return f"🥵 지금 밖이 힘든 날씨... 그래도 최선이에요 ({int(score)}점)"