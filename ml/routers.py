from fastapi import APIRouter
from ml.comfort_model import predict_comfort
from datetime import datetime

router = APIRouter()


@router.get("/predict")
def predict_single(
    month: int = None,
    hour: int = None,
    temperature: float = 25.0,
    uv_index: float = 5.0,
    has_shade: bool = False
):
    """단일 쾌적도 예측 테스트 엔드포인트"""
    now = datetime.now()
    month = month or now.month
    hour = hour or now.hour

    score = predict_comfort(month, hour, temperature, uv_index, has_shade)
    return {
        "inputs": {
            "month": month,
            "hour": hour,
            "temperature": temperature,
            "uv_index": uv_index,
            "has_shade_structure": has_shade
        },
        "comfort_score": score
    }