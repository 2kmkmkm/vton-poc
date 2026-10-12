
import base64
import io
import json
import os
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.openapi.utils import get_openapi
from fastapi.responses import Response
from openai import OpenAI, OpenAIError
from PIL import Image, UnidentifiedImageError


# --------------------------------------------------
# 1. 기본 설정
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2.5-sunburst")

AVATAR_SETTING = os.getenv("AVATAR_IMAGE_PATH", "assets/avatar.png")
AVATAR_PATH = Path(AVATAR_SETTING)

if not AVATAR_PATH.is_absolute():
    AVATAR_PATH = PROJECT_ROOT / AVATAR_PATH

SUPPORTED_CATEGORIES = ("top", "bottom", "outer", "shoes", "hat")

CATEGORY_LABELS = {
    "top": "top / shirt",
    "bottom": "bottoms / pants or skirt",
    "outer": "outer / coat or jacket",
    "shoes": "shoes",
    "hat": "hat / headwear",
}


app = FastAPI(
    title="GPT Image Virtual Try-On PoC",
    description=(
        "Edit a shared full-body avatar using up to five "
        "selected clothing categories."
    ),
    version="1.0.0",
)


# --------------------------------------------------
# 2. Swagger UI OpenAPI 설정
# --------------------------------------------------

def custom_openapi():
    """Swagger UI에서 여러 이미지 파일을 업로드할 수 있도록 설정한다."""
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    components = schema.get("components", {}).get("schemas", {})

    for component in components.values():
        properties = component.get("properties", {})

        for prop in properties.values():
            if prop.get("type") == "array":
                items = prop.get("items", {})

                if items.get("contentMediaType") == "application/octet-stream":
                    items.pop("contentMediaType", None)
                    items["format"] = "binary"

            elif prop.get("contentMediaType") == "application/octet-stream":
                prop.pop("contentMediaType", None)
                prop["format"] = "binary"

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


# --------------------------------------------------
# 3. 카테고리 파싱 및 검증
# --------------------------------------------------

def parse_categories(categories_input: str | list[str]) -> list[str]:
    """
    다음 입력 형식을 지원한다.

    JSON 배열 문자열: ["top", "bottom"]
    쉼표 구분 문자열: top,bottom
    파이썬 리스트: ["top", "bottom"]
    """
    if isinstance(categories_input, list):
        categories = categories_input

    elif isinstance(categories_input, str):
        cleaned_input = categories_input.strip()

        if not cleaned_input:
            raise HTTPException(
                status_code=400,
                detail="Select at least one category.",
            )

        try:
            if cleaned_input.startswith("["):
                categories = json.loads(cleaned_input)
            else:
                categories = [
                    item.strip()
                    for item in cleaned_input.split(",")
                    if item.strip()
                ]

        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail=(
                    'categories_json must be a valid JSON array or '
                    'comma-separated string, e.g. ["top", "shoes"] '
                    'or top,shoes.'
                ),
            ) from exc

    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid format for categories_json.",
        )

    if not isinstance(categories, list) or not categories:
        raise HTTPException(
            status_code=400,
            detail="Select at least one category.",
        )

    if len(categories) > len(SUPPORTED_CATEGORIES):
        raise HTTPException(
            status_code=400,
            detail="At most 5 categories are supported.",
        )

    if any(not isinstance(item, str) for item in categories):
        raise HTTPException(
            status_code=400,
            detail="Every category must be a string.",
        )

    unknown = [
        item for item in categories
        if item not in SUPPORTED_CATEGORIES
    ]

    if unknown:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported categories: {unknown}. "
                f"Allowed: {list(SUPPORTED_CATEGORIES)}"
            ),
        )

    if len(set(categories)) != len(categories):
        raise HTTPException(
            status_code=400,
            detail="Duplicate categories are not allowed.",
        )

    return categories


# --------------------------------------------------
# 4. 이미지 정규화
# --------------------------------------------------

def to_png_bytes(image_bytes: bytes) -> bytes:
    """
    입력 이미지의 실제 포맷을 판별하고 PNG 바이트로 변환한다.
    API에 전달할 때 파일명과 MIME 타입도 함께 지정한다.
    """
    with Image.open(io.BytesIO(image_bytes)) as image:
        image.load()

        # 투명도가 있는 이미지도 흰 배경에 합성한다.
        rgba_image = image.convert("RGBA")
        white_background = Image.new(
            "RGBA",
            rgba_image.size,
            (255, 255, 255, 255),
        )
        white_background.alpha_composite(rgba_image)

        buffer = io.BytesIO()
        white_background.convert("RGB").save(buffer, format="PNG")

        return buffer.getvalue()


# --------------------------------------------------
# 5. 이미지 편집 프롬프트
# --------------------------------------------------

def build_prompt(categories: list[str]) -> str:
    clothing_instructions = "\n".join(
        f"- Reference image {index + 2}: "
        f"{CATEGORY_LABELS[category]}"
        for index, category in enumerate(categories)
    )

    return f"""
The first input image is the base full-body avatar.
Each subsequent input image is a clothing product reference.

Clothing reference mapping:
{clothing_instructions}

Virtual try-on requirements:
- Preserve the base avatar's identity, face, hairstyle,
  body proportions, pose, facial expression, camera angle,
  and background.
- Transfer each supplied clothing item from its corresponding
  reference image onto the avatar.
- Do not invent or add items for categories that were not supplied.
- Preserve the recognizable colors, patterns, materials,
  silhouettes, and details of each product.
- If both a top and outerwear are supplied, layer the outerwear
  naturally over the top.
- Place shoes on the feet and a hat on the head.
- Make each supplied item fit naturally to the avatar's body and pose.
- Use realistic lighting, shadows, and proportions.
- Return one finished edited image, not a collage.
""".strip()


# --------------------------------------------------
# 6. 상태 확인 API
# --------------------------------------------------

@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "model": MODEL,
    }


# --------------------------------------------------
# 7. 가상 피팅 API
# --------------------------------------------------

@app.post(
    "/api/images/clothing-transfer",
    response_class=Response,
    responses={
        200: {"content": {"image/png": {}}},
        400: {
            "description": "Invalid categories or product images."
        },
        500: {
            "description": "Avatar image or API configuration is missing."
        },
        502: {
            "description": "Image API request failed."
        },
    },
)
async def clothing_transfer(
    categories_json: Annotated[
        str,
        Form(
            description=(
                'JSON array, e.g. ["top", "outer", "shoes"]. '
                "Comma-separated values are also accepted."
            )
        ),
    ],
    clothing_images: Annotated[
        list[UploadFile],
        File(
            description=(
                "Product images in the same order as categories_json."
            )
        ),
    ],
) -> Response:

    # 1. 카테고리 검증
    categories = parse_categories(categories_json)

    if len(clothing_images) != len(categories):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Received {len(clothing_images)} product images for "
                f"{len(categories)} categories. Counts must match."
            ),
        )

    # 2. 아바타 파일 확인
    if not AVATAR_PATH.is_file():
        raise HTTPException(
            status_code=500,
            detail=f"Shared avatar image not found: {AVATAR_PATH}",
        )

    # 3. API 키 확인
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY is not configured.",
        )

    try:
        # 4. 아바타 이미지 읽기 및 PNG 변환
        avatar_bytes = AVATAR_PATH.read_bytes()

        try:
            avatar_png = to_png_bytes(avatar_bytes)
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise HTTPException(
                status_code=500,
                detail="The configured avatar image is invalid.",
            ) from exc

        # 5. 업로드된 의류 이미지 읽기 및 PNG 변환
        clothing_png_list: list[bytes] = []

        for index, upload in enumerate(clothing_images):
            content_type = upload.content_type or ""

            if not content_type.startswith("image/"):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Product image {index + 1} "
                        "is not an image upload."
                    ),
                )

            content = await upload.read()

            if not content:
                raise HTTPException(
                    status_code=400,
                    detail=f"Product image {index + 1} is empty.",
                )

            try:
                clothing_png = to_png_bytes(content)
            except (UnidentifiedImageError, OSError, ValueError) as exc:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Product image {index + 1} "
                        "is not a valid image."
                    ),
                ) from exc

            clothing_png_list.append(clothing_png)

        # 6. 아바타 + 개별 의류 이미지 전달
        # image[0] = 아바타
        # image[1:] = categories_json에 적힌 순서의 의류 이미지
        image_inputs = [
            ("avatar.png", avatar_png, "image/png")
        ]

        for index, clothing_png in enumerate(clothing_png_list):
            image_inputs.append(
                (
                    f"clothing_{index + 1}.png",
                    clothing_png,
                    "image/png",
                )
            )

        client = OpenAI(api_key=api_key)

        result = client.images.edit(
            model=MODEL,
            image=image_inputs,
            prompt=build_prompt(categories),
            n=1,
            size="1024x1536",
            quality="high",
            output_format="png",
        )

        # 7. 결과 이미지 Base64 디코딩
        if not result.data or not result.data[0].b64_json:
            raise HTTPException(
                status_code=502,
                detail="The image API returned no image data.",
            )

        image_bytes = base64.b64decode(
            result.data[0].b64_json
        )

        # 8. PNG 응답 반환
        return Response(
            content=image_bytes,
            media_type="image/png",
            headers={
                "Content-Disposition": 'inline; filename="try-on.png"'
            },
        )

    except HTTPException:
        raise

    except OpenAIError as exc:
        print(
            f"OpenAI image edit failed: "
            f"{type(exc).__name__}: {exc}"
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "OpenAI image edit request failed "
                f"({type(exc).__name__})."
            ),
        ) from exc

    except Exception as exc:
        print(
            f"Unexpected clothing transfer error: "
            f"{type(exc).__name__}: {exc}"
        )

        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred during image processing.",
        ) from exc

    finally:
        for upload in clothing_images:
            await upload.close()


# --------------------------------------------------
# 8. 직접 실행
# --------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
    )
 