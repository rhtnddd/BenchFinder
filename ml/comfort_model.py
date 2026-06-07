import numpy as np
import joblib
import os
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error

MODEL_PATH = os.path.join(os.path.dirname(__file__), "comfort_model.pkl")


def generate_synthetic_data(n=300):
    """
    규칙 기반 가상 데이터셋 생성
    Features: month, hour, temperature, uv_index, has_shade_structure
    Target: comfort_score (0~100)
    """
    np.random.seed(42)
    data = []

    for _ in range(n):
        month = np.random.randint(1, 13)
        hour = np.random.randint(6, 22)
        temperature = np.random.uniform(5, 38)
        uv_index = np.random.uniform(0, 11)
        has_shade = np.random.choice([0, 1])

        # 규칙 기반 쾌적도 계산
        score = 100.0

        # 온도 패널티: 26도 이상부터 급격히 하락
        if temperature > 26:
            score -= (temperature - 26) * 3.5
        elif temperature < 10:
            score -= (10 - temperature) * 2.0

        # 자외선 패널티
        score -= uv_index * 4.0

        # 그늘막 없을 때 자외선 높으면 추가 패널티
        if not has_shade and uv_index > 5:
            score -= (uv_index - 5) * 5.0

        # 시간대 패널티 (정오 전후 가장 힘듦)
        if 11 <= hour <= 15:
            score -= 15
            if not has_shade:
                score -= 10

        # 아침/저녁 보너스
        if hour < 9 or hour > 18:
            score += 10

        # 그늘막 있으면 쾌적도 보너스
        if has_shade:
            score += 15

        # 여름철(7~8월) 패널티
        if month in [7, 8]:
            score -= 10
        # 봄/가을 보너스
        elif month in [4, 5, 9, 10]:
            score += 8

        # 노이즈 추가
        score += np.random.normal(0, 5)

        # 0~100 클리핑
        score = float(np.clip(score, 0, 100))

        data.append([month, hour, temperature, uv_index, has_shade, score])

    return np.array(data)


def train_and_save_model():
    """모델 학습 후 pkl로 저장"""
    data = generate_synthetic_data(300)
    X = data[:, :5]
    y = data[:, 5]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    print(f"모델 RMSE: {rmse:.2f}")

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    return model


def load_model():
    """저장된 모델 로드"""
    if not os.path.exists(MODEL_PATH):
        return train_and_save_model()
    return joblib.load(MODEL_PATH)


def predict_comfort(month: int, hour: int, temperature: float,
                    uv_index: float, has_shade: bool) -> float:
    """단일 벤치의 쾌적도 점수 예측"""
    model = load_model()
    features = np.array([[month, hour, temperature, uv_index, int(has_shade)]])
    score = model.predict(features)[0]
    return round(float(np.clip(score, 0, 100)), 1)