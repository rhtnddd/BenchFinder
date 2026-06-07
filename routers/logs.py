from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
from datetime import datetime
from models.database import get_db
from models.db_models import UserLog

router = APIRouter()


class LogResponse(BaseModel):
    id: int
    rest_area_id: int
    current_lat: float
    current_lng: float
    session_id: str
    comfort_score: float | None
    distance_m: float | None
    discharged_at: datetime

    class Config:
        from_attributes = True


@router.get("/", response_model=List[LogResponse])
def get_all_logs(limit: int = 20, db: Session = Depends(get_db)):
    """최근 방전 로그 조회"""
    return db.query(UserLog).order_by(UserLog.discharged_at.desc()).limit(limit).all()


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """통계: 총 방전 횟수, 가장 인기 있는 휴식처"""
    total_logs = db.query(UserLog).count()

    # 가장 많이 추천된 휴식처
    from sqlalchemy import func
    from models.db_models import RestArea

    popular = (
        db.query(RestArea.name, func.count(UserLog.id).label("visit_count"))
        .join(UserLog, RestArea.id == UserLog.rest_area_id)
        .group_by(RestArea.id)
        .order_by(func.count(UserLog.id).desc())
        .limit(5)
        .all()
    )

    return {
        "total_discharge_events": total_logs,
        "popular_spots": [{"name": p[0], "visits": p[1]} for p in popular]
    }