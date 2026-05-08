"""
Soniva Backend - Main Application Entry Point
"""
import os
import re
import traceback
import logging
from typing import AsyncIterator
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, StreamingResponse
from contextlib import asynccontextmanager
from pathlib import Path

from app.config import settings
from app.database import engine, Base
from app.api.api_v1.api import api_router

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup: Create database tables
    Base.metadata.create_all(bind=engine)

    # Create upload directories
    upload_dirs = [
        Path(settings.LOCAL_STORAGE_PATH) / "voice",
        Path(settings.LOCAL_STORAGE_PATH) / "avatars",
        Path(settings.LOCAL_STORAGE_PATH) / "voice_cards",
        Path(settings.LOCAL_STORAGE_PATH) / "posts",
    ]
    for dir_path in upload_dirs:
        dir_path.mkdir(parents=True, exist_ok=True)

    yield

    # Shutdown: cleanup if needed
    pass


app = FastAPI(
    title="Soniva API",
    description="声韵 - AI声音社交应用后端API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Voice file route with HTTP Range support.
#
# Why this exists: iOS AVPlayer (used by `audioplayers`) refuses to start
# playback unless the server advertises `Accept-Ranges: bytes` and
# replies to a Range request with `206 Partial Content`. Starlette
# 0.36's `StaticFiles` doesn't implement Range — it always returns the
# whole file with a `200`, which AVPlayer reports as
# `Failed to set playerItem (AVPlayerItem.Status.failed)`.
#
# We register this route *before* the `/uploads` static mount so it
# wins on path resolution; the rest of `/uploads/...` (avatars, voice
# cards) keeps using the default static handler.
# ---------------------------------------------------------------------------

# audio/mp4a-latm (the default Python mimetypes returns for .m4a) is the
# raw-AAC ADTS MIME, which AVPlayer rejects. m4a files are MP4 audio
# containers, so we map the right type explicitly.
_AUDIO_CONTENT_TYPES = {
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
}

_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")
_VOICE_DIR = Path(settings.LOCAL_STORAGE_PATH) / "voice"


def _stream_file(path: Path, start: int, end: int) -> AsyncIterator[bytes]:
    """Yield bytes from `start` (inclusive) to `end` (inclusive). 64KB
    chunks so we never load a long voice clip into memory."""
    chunk = 64 * 1024

    async def gen():
        remaining = end - start + 1
        with path.open("rb") as f:
            f.seek(start)
            while remaining > 0:
                data = f.read(min(chunk, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    return gen()


@app.get("/uploads/voice/{filename:path}")
async def serve_voice_file(filename: str, request: Request):
    # Block path traversal — `filename` is stitched into a Path so any
    # `..` would escape the voice dir.
    safe_name = filename.replace("..", "").lstrip("/")
    file_path = _VOICE_DIR / safe_name
    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voice file not found",
        )

    file_size = file_path.stat().st_size
    ext = file_path.suffix.lower()
    content_type = _AUDIO_CONTENT_TYPES.get(ext, "application/octet-stream")

    range_header = request.headers.get("range")
    if not range_header:
        # No range → return the whole file but still advertise Range
        # support so AVPlayer knows to ask for it on the next GET.
        return StreamingResponse(
            _stream_file(file_path, 0, file_size - 1),
            status_code=status.HTTP_200_OK,
            media_type=content_type,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(file_size),
                "Cache-Control": "public, max-age=3600",
            },
        )

    m = _RANGE_RE.fullmatch(range_header.strip())
    if not m:
        raise HTTPException(status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE)
    start_str, end_str = m.groups()
    start = int(start_str) if start_str else 0
    end = int(end_str) if end_str else file_size - 1
    if start >= file_size or end >= file_size or start > end:
        return JSONResponse(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            content={"detail": "Range out of bounds"},
            headers={"Content-Range": f"bytes */{file_size}"},
        )

    length = end - start + 1
    return StreamingResponse(
        _stream_file(file_path, start, end),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=content_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(length),
            "Cache-Control": "public, max-age=3600",
        },
    )


# Mount static files for uploads (avatars, voice_cards, posts).
# Voice files have their own Range-aware route registered above.
uploads_path = Path(settings.LOCAL_STORAGE_PATH)
if uploads_path.exists():
    app.mount("/uploads", StaticFiles(directory=str(uploads_path)), name="uploads")

# Include API router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


# Global exception handler for debugging
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all exceptions and return detailed error in debug mode"""
    error_detail = str(exc)
    if settings.DEBUG:
        error_detail = f"{str(exc)}\n\nTraceback:\n{traceback.format_exc()}"
    print(f"[ERROR] {request.method} {request.url}: {exc}")
    print(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": "Internal Server Error",
            "detail": error_detail if settings.DEBUG else "An error occurred"
        }
    )


@app.get("/")
def root():
    """Root endpoint"""
    return {
        "name": "Soniva API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
