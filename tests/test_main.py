import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from dotenv import load_dotenv

from app.main import app

# 프로젝트 루트의 .env 로드
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

client = TestClient(app)

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "app" / "data"


@pytest.fixture
def sample_images():
    """app/data/ 폴더에 있는 5가지 실제 상품 이미지 파일들을 바이트로 로드합니다."""
    image_names = ["top.png", "bottom.png", "outer.png", "shoes.png", "hat.png"]
    images = {}

    for name in image_names:
        file_path = DATA_DIR / name
        if not file_path.is_file():
            pytest.skip(f"테스트 이미지 파일이 없습니다: {file_path}")
        images[name] = file_path.read_bytes()

    return images


def test_health_check():
    """헬스체크 엔드포인트가 정상 작동하는지 확인합니다."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_clothing_transfer_real_api(sample_images):
    """
    실제 OpenAI API를 호출하여 가상 피팅 결과 이미지를 받아오는지 검증합니다.
    (주의: 실제 API 비용이 발생하며, API 키 및 네트워크 상태에 따라 시간이 다소 소요될 수 있습니다.)
    """
    # 1. 환경 변수에 실제 API 키가 설정되어 있는지 확인
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY가 설정되어 있지 않아 실제 API 테스트를 건너뜁니다.")

    # 2. 전송할 카테고리 설정 (5가지 모두 포함)
    categories_json_str = '["outer", "top", "bottom", "shoes", "hat"]'

    # 3. 멀티파트 파일 페이로드 구성
    files = [
        ("clothing_images", ("outer.png", sample_images["outer.png"], "image/png")),
        ("clothing_images", ("top.png", sample_images["top.png"], "image/png")),
        ("clothing_images", ("bottom.png", sample_images["bottom.png"], "image/png")),
        ("clothing_images", ("shoes.png", sample_images["shoes.png"], "image/png")),
        ("clothing_images", ("hat.png", sample_images["hat.png"], "image/png")),
    ]

    data = {
        "categories_json": categories_json_str
    }

    # 4. 실제 API 호출 (타임아웃을 넉넉히 설정하거나 기본값 사용)
    response = client.post("/api/images/clothing-transfer", data=data, files=files)

    # 5. 결과 검증
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert len(response.content) > 0

    output_path = BASE_DIR / "tests" / "result_try_on.png"
    output_path.write_bytes(response.content)