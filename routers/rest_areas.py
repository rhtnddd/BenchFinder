import csv
import io
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from models.database import get_db
from models.db_models import RestArea

router = APIRouter()


class RestAreaCreate(BaseModel):
    name: str
    latitude: float
    longitude: float
    type: str = "벤치"
    has_shade_structure: bool = False
    address: Optional[str] = None
    description: Optional[str] = None


class RestAreaResponse(BaseModel):
    id: int
    name: str
    latitude: float
    longitude: float
    type: str
    has_shade_structure: bool
    address: Optional[str]
    description: Optional[str]

    class Config:
        from_attributes = True


def _has_shade(facility_str: str) -> bool:
    """
    공원보유시설(편익시설) 컬럼에서 그늘막 여부 판단
    '파고라', '정자', '그늘막', '쉼터' 키워드 포함 시 True
    """
    if not facility_str:
        return False
    keywords = ["파고라", "정자", "그늘막", "쉼터", "퍼걸러"]
    return any(k in facility_str for k in keywords)


def _parse_type(park_type: str, facility_str: str) -> str:
    """
    공원구분 + 시설 정보로 RestArea type 결정
    """
    if "파고라" in facility_str or "정자" in facility_str:
        return "정자"
    if "체육" in park_type:
        return "잔디"
    return "벤치"


@router.get("/", response_model=List[RestAreaResponse])
def get_all_rest_areas(db: Session = Depends(get_db)):
    """전체 휴식처 목록 조회"""
    return db.query(RestArea).all()


@router.post("/", response_model=RestAreaResponse)
def create_rest_area(area: RestAreaCreate, db: Session = Depends(get_db)):
    """새 휴식처 등록"""
    db_area = RestArea(**area.model_dump())
    db.add(db_area)
    db.commit()
    db.refresh(db_area)
    return db_area


@router.get("/{area_id}", response_model=RestAreaResponse)
def get_rest_area(area_id: int, db: Session = Depends(get_db)):
    area = db.query(RestArea).filter(RestArea.id == area_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="휴식처를 찾을 수 없어요")
    return area


@router.post("/upload-csv")
async def upload_csv(
        file: UploadFile = File(...),
        db: Session = Depends(get_db)
):
    """
    공공데이터 CSV 업로드 → DB 마이그레이션

    지원 컬럼 (공원정보 표준데이터):
    관리번호, 공원명, 공원구분, 소재지도로명주소, 소재지지번주소,
    위도, 경도, 공원보유시설(편익시설) 등
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="CSV 파일만 업로드 가능해요")

    content = await file.read()

    # 인코딩 자동 감지 (공공데이터는 주로 EUC-KR 또는 UTF-8-SIG)
    for encoding in ["utf-8-sig", "euc-kr", "utf-8", "cp949"]:
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise HTTPException(status_code=400, detail="파일 인코딩을 읽을 수 없어요 (UTF-8 또는 EUC-KR로 저장해주세요)")

    # 중복 체크를 위한 기존 데이터 로드 (이름, 위도, 경도 조합)
    existing = db.query(RestArea.name, RestArea.latitude, RestArea.longitude).all()
    existing_set = set(existing)

    reader = csv.DictReader(io.StringIO(text))

    inserted = 0
    skipped = 0
    duplicates = 0
    errors = []

    for i, row in enumerate(reader):
        try:
            # 위도/경도 파싱 (빈 값이면 스킵)
            lat_str = row.get("위도", "").strip()
            lng_str = row.get("경도", "").strip()
            if not lat_str or not lng_str:
                skipped += 1
                continue

            lat = float(lat_str)
            lng = float(lng_str)

            # 위도/경도 유효 범위 체크 (한국: 위도 33~39, 경도 124~132)
            if not (33.0 <= lat <= 39.0 and 124.0 <= lng <= 132.0):
                skipped += 1
                continue

            # 이름
            name = row.get("공원명", "").strip() or row.get("시설명", "").strip()
            if not name:
                skipped += 1
                continue

            # 중복 체크
            if (name, lat, lng) in existing_set:
                duplicates += 1
                continue

            # 주소: 도로명 우선, 없으면 지번
            address = (
                    row.get("소재지도로명주소", "").strip()
                    or row.get("소재지지번주소", "").strip()
                    or None
            )

            # 편익시설 컬럼 (그늘막 여부 판단용)
            facility = row.get("공원보유시설(편익시설)", "").strip()
            park_type = row.get("공원구분", "").strip()

            area = RestArea(
                name=name,
                latitude=lat,
                longitude=lng,
                type=_parse_type(park_type, facility),
                has_shade_structure=_has_shade(facility),
                address=address,
                description=park_type or None
            )
            db.add(area)
            inserted += 1
            # 새로 추가된 것도 세트에 넣어 이번 배치 내 중복 방지
            existing_set.add((name, lat, lng))

        except (ValueError, KeyError) as e:
            errors.append(f"행 {i + 2}: {str(e)}")
            skipped += 1
            continue

    db.commit()

    return {
        "message": f"CSV 업로드 완료!",
        "inserted": inserted,
        "skipped": skipped,
        "duplicates": duplicates,
        "errors": errors[:10]  # 에러는 최대 10개만 반환
    }


@router.delete("/all")
def delete_all(db: Session = Depends(get_db)):
    """전체 데이터 초기화 (재업로드 전 사용)"""
    count = db.query(RestArea).count()
    db.query(RestArea).delete()
    db.commit()
    return {"message": f"🗑️ {count}개 데이터 삭제 완료"}