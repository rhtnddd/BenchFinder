from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from models.database import engine, Base
from routers import rest_areas, recommend, logs
from ml.comfort_model import train_and_save_model

# DB 테이블 생성
Base.metadata.create_all(bind=engine)

# ML 모델 학습 (pkl 없으면 자동 생성)
if not os.path.exists("ml/comfort_model.pkl"):
    print("ML 모델 학습 중...")
    train_and_save_model()
    print("ML 모델 저장 완료!")

# 기상청 API 키 환경변수 안내
kma_key = os.getenv("KMA_API_KEY", "")
if not kma_key:
    print("KMA_API_KEY 환경변수가 없어요 → mock 날씨 데이터로 동작합니다")
    print("실제 연동하려면: export KMA_API_KEY=발급받은키")
else:
    print(f"기상청 API 키 로드 완료 ({kma_key[:6]}...)")

app = FastAPI(
    title="합법적 누울 자리 API",
    description="전국 벤치 & 휴식처 망원경",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rest_areas.router, prefix="/api/rest-areas", tags=["휴식처"])
app.include_router(recommend.router, prefix="/api/recommend", tags=["추천"])
app.include_router(logs.router, prefix="/api/logs", tags=["방전로그"])

frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    # /static 경로로 frontend 폴더 안의 자원들을 정상 서빙
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")

@app.get("/")
async def root():
    index_path = os.path.join(frontend_path, "index.html")
    if os.path.exists(index_path):
        # [보완] 브라우저가 순수 웹 HTML 문서로 완벽하게 인식하도록 타입을 지정해서 리턴
        return FileResponse(index_path, media_type="text/html")
    return {"message": "합법적 누울 자리 API 서버 작동 중"}

@app.get("/health")
async def health_check():
    kma = "연결됨" if os.getenv("KMA_API_KEY") else "미설정 (mock 사용) ⚠️"
    return {"status": "ok", "kma_api": kma}