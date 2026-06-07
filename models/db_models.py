from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from models.database import Base


class RestArea(Base):
    """휴식처 테이블 - 벤치, 정자, 잔디광장 등"""
    __tablename__ = "rest_areas"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)           # 장소명
    latitude = Column(Float, nullable=False)         # 위도
    longitude = Column(Float, nullable=False)        # 경도
    type = Column(String, default="벤치")            # 벤치 / 정자 / 잔디
    has_shade_structure = Column(Boolean, default=False)  # 고정 그늘막 여부
    address = Column(String, nullable=True)          # 주소 (선택)
    description = Column(String, nullable=True)      # 설명 (선택)

    # 중복 방지: 이름 + 좌표 조합이 겹치지 않도록 설정
    __table_args__ = (
        UniqueConstraint('name', 'latitude', 'longitude', name='_name_lat_lng_uc'),
    )

    # 1:N 관계 - 하나의 휴식처에 여러 방전 로그
    logs = relationship("UserLog", back_populates="rest_area")


class UserLog(Base):
    """방전 로그 테이블 - 사용자가 누른 '배터리 5%' 기록"""
    __tablename__ = "user_logs"

    id = Column(Integer, primary_key=True, index=True)
    rest_area_id = Column(Integer, ForeignKey("rest_areas.id"), nullable=False)
    current_lat = Column(Float, nullable=False)       # 사용자 현재 위도
    current_lng = Column(Float, nullable=False)       # 사용자 현재 경도
    session_id = Column(String, nullable=False)       # 가상 유저 식별자
    comfort_score = Column(Float, nullable=True)      # 추천 당시 쾌적도 점수
    distance_m = Column(Float, nullable=True)         # 추천 당시 거리(m)
    discharged_at = Column(DateTime, default=datetime.utcnow)

    # N:1 관계
    rest_area = relationship("RestArea", back_populates="logs")