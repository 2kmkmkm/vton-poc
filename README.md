# GPT Image Virtual Try-On PoC

FastAPI와 OpenAI Image Edit API를 활용하여, 공유된 단일 전신 아바타 이미지에 최대 5가지 의류 카테고리(top, bottom, outer, shoes, hat)를 자연스럽게 합성(가상 피팅)하는 Proof of Concept(PoC) 백엔드 애플리케이션입니다.

---

## 🛠 Tech Stack & Architecture

- **Language**: Python 3.13+
- **Framework**: FastAPI (Asynchronous Web Framework)
- **Image Processing**: Pillow (PIL) - 투명도 처리 및 PNG 정규화 (`to_png_bytes`)
- **AI Model**: OpenAI Image Edit API (`gpt-image-2.5-sunburst`)
- **Testing**: Pytest, FastAPI TestClient

---

## 📁 File Structure

```text
gpt-image-tryon-python/
├── app/
│   ├── data/                 # 샘플 상품 이미지 (top, bottom, outer, shoes, hat)
│   │   ├── bottom.png
│   │   ├── hat.png
│   │   ├── outer.png
│   │   ├── shoes.png
│   │   └── top.png
│   ├── __init__.py
│   └── main.py               # FastAPI 서버 및 비즈니스 로직 진입점
├── assets/
│   └── avatar.png            # 기본 공유 전신 아바타 이미지
├── tests/
│   ├── result_try_on.png     # 실제 API 테스트 후 생성된 결과 이미지 (Git Ignore 대상)
│   └── test_main.py          # Pytest 통합 테스트 코드
├── .env                      # 환경 변수 설정 파일 (OPENAI_API_KEY)
├── .gitignore                # Git 제외 파일 설정
├── README.md                 # 프로젝트 문서
└── requirements.txt          # 패키지 의존성 목록
```

---

## ⚙️ Getting Started & Prerequisites

본 프로젝트를 로컬 환경에서 실행하고 테스트하기 위해 거쳐야 하는 사전 준비 및 명령어 순서입니다.

### 1. 저장소 클론 및 프로젝트 폴더 이동
터미널을 열고 프로젝트의 최상위 루트 폴더로 이동합니다.
```powershell
cd gpt-image-tryon-python
```

### 2. 필수 라이브러리 설치
프로젝트 구동 및 테스트에 필요한 패키지들을 `requirements.txt`를 통해 일괄 설치합니다.
```powershell
pip install -r requirements.txt
```

### 3. 환경 변수(`.env`) 설정
프로젝트 최상위 루트 폴더에 `.env` 파일을 생성하고, 아래 양식에 맞춰 본인의 OpenAI API Key 및 설정을 작성합니다.
```env
OPENAI_API_KEY=your-real-openai-api-key-here
OPENAI_IMAGE_MODEL=gpt-image-2.5-sunburst
AVATAR_IMAGE_PATH=assets/avatar.png
```

---

## 🚀 Usage & Testing

### 1. FastAPI 서버 실행 (main 코드)
로컬에서 서버를 구동하여 API를 직접 테스트하려면 아래 명령어를 입력합니다.
```powershell
python -m uvicorn app.main:app --reload
```
* 서버 주소: `http://127.0.0.1:8000`

#### 🌐 Swagger UI를 통한 테스트 순서 및 방법
1. 브라우저에서 **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)** 접속
2. `POST /api/images/clothing-transfer` 엔드포인트 클릭 후 **[Try it out]** 선택
3. **`categories_json`** 입력란에 선택할 카테고리 배열 입력 (JSON 또는 쉼표 구분)
   * *예시:* `["outer", "top", "bottom", "shoes", "hat"]` 또는 `outer,top,bottom,shoes,hat`
4. **`clothing_images`** 파일 업로드란에 카테고리 순서에 맞는 이미지 파일(`top.png`, `bottom.png` 등)을 각각 선택하여 업로드
5. **[Execute]** 버튼을 눌러 결과 확인 및 다운로드

---

### 2. Pytest 통합 테스트 실행 (`test_main`)
로컬 `app/data/`에 있는 5가지 상품 이미지와 실제 OpenAI API를 연동하여 E2E 테스트를 수행합니다.

#### 🧪 테스트 실행 순서 및 방법
최상위 루트 폴더에서 아래 명령어를 실행합니다.
```powershell
python -m pytest
```
* **결과물:** 테스트가 정상적으로 완료되면 `tests/result_try_on.png` 경로에 실제 OpenAI API가 편집해 반환한 가상 피팅 결과 이미지가 자동으로 저장됩니다.