from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import uuid
from datetime import datetime

from models.database import get_db
from models.db_models import RestArea, UserLog
from ml.ml_service import (
    get_weather_data, haversine_distance,
    score_rest_areas, get_comfort_message
)

router = APIRouter()

SEARCH_RADIUS_M = 500  # 탐색 반경 (미터)
MAX_RESULTS = 5        # 최대 추천 개수


class RecommendRequest(BaseModel):
    latitude: float
    longitude: float
    session_id: Optional[str] = None
    radius_m: Optional[int] = 500


class RecommendResult(BaseModel):
    id: int
    name: str
    latitude: float
    longitude: float
    type: str
    has_shade_structure: bool
    address: Optional[str]
    comfort_score: float
    distance_m: float
    comfort_message: str
    kakao_map_url: str


class RecommendResponse(BaseModel):
    session_id: str
    weather: dict
    results: List[RecommendResult]
    total_found: int
    searched_radius_m: int


@router.post("/", response_model=RecommendResponse)
async def recommend_rest_area(req: RecommendRequest, db: Session = Depends(get_db)):
    """
    핵심 API: 사용자 위치 기반 최적 휴식처 추천
    1. 반경 내 RestArea 조회 (Bounding Box로 DB 필터링 최적화)
    2. 실시간 날씨 데이터 가져오기
    3. ML 모델로 쾌적도 점수 계산
    4. 중복 이름 제거로 결과 다양성 확보
    5. UserLog 기록 및 결과 반환
    """
    session_id = req.session_id or str(uuid.uuid4())[:8]
    radius = req.radius_m or SEARCH_RADIUS_M

    # 1. Bounding Box를 사용하여 DB 조회 최적화 (18k개 전체 로드 방지)
    # 1km 당 위도 약 0.009도, 경도 약 0.011도 차이 (안전하게 2배 반경)
    lat_margin = (radius / 1000.0) * 0.018
    lng_margin = (radius / 1000.0) * 0.022

    query_results = db.query(RestArea).filter(
        RestArea.latitude.between(req.latitude - lat_margin, req.latitude + lat_margin),
        RestArea.longitude.between(req.longitude - lng_margin, req.longitude + lng_margin)
    ).all()

    nearby = []
    for area in query_results:
        dist = haversine_distance(req.latitude, req.longitude, area.latitude, area.longitude)
        if dist <= radius:
            area._distance = dist
            nearby.append(area)

    # 반경 내 결과 없으면 전체에서 가장 가까운 5개 (기존 로직 유지)
    if not nearby:
        all_areas = db.query(RestArea).all()
        for area in all_areas:
            area._distance = haversine_distance(req.latitude, req.longitude, area.latitude, area.longitude)
        nearby = sorted(all_areas, key=lambda a: a._distance)[:MAX_RESULTS]
        radius = int(nearby[-1]._distance) + 1 if nearby else radius

    # 2. 날씨 데이터 가져오기
    weather = await get_weather_data(req.latitude, req.longitude)

    # 3. ML 스코어링
    scored_all = score_rest_areas(nearby, weather)

    # 4. 결과 다양성 확보: 이름이 같은 장소는 가장 가까운 것 하나만 남김
    seen_names = set()
    scored = []
    for item in scored_all:
        if item["area"].name not in seen_names:
            scored.append(item)
            seen_names.add(item["area"].name)
        if len(scored) >= MAX_RESULTS:
            break

    # 5. UserLog 기록 (최고 추천 1개)
    if scored:
        best = scored[0]
        log = UserLog(
            rest_area_id=best["area"].id,
            current_lat=req.latitude,
            current_lng=req.longitude,
            session_id=session_id,
            comfort_score=best["comfort_score"],
            distance_m=best["distance_m"],
            discharged_at=datetime.utcnow()
        )
        db.add(log)
        db.commit()

    # 6. 응답 생성
    results = []
    for item in scored:
        area = item["area"]
        kakao_url = (
            f"https://map.kakao.com/link/to/{area.name},{area.latitude},{area.longitude}"
        )
        results.append(RecommendResult(
            id=area.id,
            name=area.name,
            latitude=area.latitude,
            longitude=area.longitude,
            type=area.type,
            has_shade_structure=area.has_shade_structure,
            address=area.address,
            comfort_score=item["comfort_score"],
            distance_m=round(item["distance_m"], 1),
            comfort_message=get_comfort_message(item["comfort_score"], area.has_shade_structure),
            kakao_map_url=kakao_url
        ))

    return RecommendResponse(
        session_id=session_id,
        weather=weather,
        results=results,
        total_found=len(nearby),
        searched_radius_m=radius
    )