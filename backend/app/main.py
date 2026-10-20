from __future__ import annotations

import base64
import binascii
import hmac
import os
import uuid
from contextlib import asynccontextmanager
from io import BytesIO
from typing import Annotated
from urllib.parse import quote

import asyncpg
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from minio import Minio
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

DATABASE_URL = os.environ["DATABASE_URL"]
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "change-this-minio-password")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "catalog")
MINIO_PUBLIC_URL = os.getenv("MINIO_PUBLIC_URL", "http://localhost:9000").rstrip("/")
ADMIN_API_TOKEN = os.getenv("ADMIN_API_TOKEN", "")
CORS_ORIGINS = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if origin.strip()]
MAX_IMAGE_BYTES = 10 * 1024 * 1024

minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10, command_timeout=15)
    yield
    await app.state.db.close()


app = FastAPI(title="Catalog API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Token"],
)


class Product(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    image_url: str
    created_at: str


class ProductList(BaseModel):
    items: list[Product]
    limit: int
    offset: int


class ProductCreateInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    image_base64: str
    source_chat_id: int | None = None
    source_message_id: int | None = None


async def require_admin_token(
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> None:
    if not ADMIN_API_TOKEN or not x_admin_token or not hmac.compare_digest(x_admin_token, ADMIN_API_TOKEN):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


def _image_type(data: bytes) -> tuple[str, str]:
    # Check image signatures, rather than trusting the client-provided MIME type.
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    raise HTTPException(status_code=415, detail="Upload a valid JPEG, PNG, or WebP image")


def _upload_image(key: str, data: bytes, content_type: str) -> None:
    minio_client.put_object(
        MINIO_BUCKET,
        key,
        BytesIO(data),
        length=len(data),
        content_type=content_type,
    )


def _remove_image(key: str) -> None:
    minio_client.remove_object(MINIO_BUCKET, key)


def _image_url(key: str) -> str:
    return f"{MINIO_PUBLIC_URL}/{quote(MINIO_BUCKET)}/{quote(key)}"


def _serialize_product(row: asyncpg.Record) -> Product:
    return Product(
        id=row["id"],
        title=row["title"],
        image_url=_image_url(row["image_key"]),
        created_at=row["created_at"].isoformat(),
    )


@app.get("/health")
async def health(request: Request) -> dict[str, str]:
    # Include PostgreSQL connectivity so a container is not marked healthy when its DB pool is broken.
    await request.app.state.db.fetchval("SELECT 1")
    return {"status": "ok"}


@app.get("/api/products", response_model=ProductList)
async def list_products(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> ProductList:
    pool: asyncpg.Pool = request.app.state.db
    rows = await pool.fetch(
        """
        SELECT id, title, image_key, created_at
        FROM products
        ORDER BY created_at DESC, id DESC
        LIMIT $1 OFFSET $2
        """,
        limit,
        offset,
    )
    return ProductList(items=[_serialize_product(row) for row in rows], limit=limit, offset=offset)


@app.get("/api/products/{product_id}", response_model=Product)
async def get_product(product_id: int, request: Request) -> Product:
    if product_id < 1:
        raise HTTPException(status_code=404, detail="Product not found")
    pool: asyncpg.Pool = request.app.state.db
    row = await pool.fetchrow(
        "SELECT id, title, image_key, created_at FROM products WHERE id = $1",
        product_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return _serialize_product(row)


@app.post("/api/admin/products", response_model=Product, status_code=status.HTTP_201_CREATED)
async def create_product(
    request: Request,
    payload: ProductCreateInput,
    _authorized: Annotated[None, Depends(require_admin_token)],
) -> Product:
    # JSON/base64 keeps uploads in process memory; uploaded files are never spooled to the container filesystem.
    source_chat_id = payload.source_chat_id
    source_message_id = payload.source_message_id
    if (source_chat_id is None) != (source_message_id is None):
        raise HTTPException(status_code=422, detail="source_chat_id and source_message_id must be sent together")
    pool: asyncpg.Pool = request.app.state.db

    if source_chat_id is not None and source_message_id is not None:
        existing = await pool.fetchrow(
            "SELECT id, title, image_key, created_at FROM products WHERE source_chat_id = $1 AND source_message_id = $2",
            source_chat_id,
            source_message_id,
        )
        if existing:
            return _serialize_product(existing)

    clean_title = payload.title.strip()
    if not clean_title:
        raise HTTPException(status_code=422, detail="Product title cannot be empty")
    max_encoded_length = ((MAX_IMAGE_BYTES + 2) // 3) * 4
    if len(payload.image_base64) > max_encoded_length:
        raise HTTPException(status_code=413, detail="Image must be 10 MB or smaller")
    try:
        content = base64.b64decode(payload.image_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=422, detail="image_base64 must contain valid Base64 data") from None
    if not content:
        raise HTTPException(status_code=422, detail="Image is empty")
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image must be 10 MB or smaller")
    extension, content_type = _image_type(content)
    image_key = f"products/{uuid.uuid4().hex}.{extension}"

    await run_in_threadpool(_upload_image, image_key, content, content_type)
    try:
        row = await pool.fetchrow(
            """
            INSERT INTO products (title, image_key, source_chat_id, source_message_id)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (source_chat_id, source_message_id) DO NOTHING
            RETURNING id, title, image_key, created_at
            """,
            clean_title,
            image_key,
            source_chat_id,
            source_message_id,
        )
        if row is not None:
            return _serialize_product(row)

        # Another replica may have created the same Telegram-originated product first.
        await run_in_threadpool(_remove_image, image_key)
        if source_chat_id is not None and source_message_id is not None:
            existing = await pool.fetchrow(
                "SELECT id, title, image_key, created_at FROM products WHERE source_chat_id = $1 AND source_message_id = $2",
                source_chat_id,
                source_message_id,
            )
            if existing:
                return _serialize_product(existing)
        raise HTTPException(status_code=409, detail="Product already exists")
    except HTTPException:
        raise
    except Exception:
        # Compensate if DB insert failed after object upload, avoiding an orphaned object.
        try:
            await run_in_threadpool(_remove_image, image_key)
        except Exception:
            pass
        raise
