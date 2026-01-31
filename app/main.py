"""
Soniva Backend - Main Application Entry Point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pathlib import Path

from app.config import settings
from app.database import engine, Base
from app.api.api_v1.api import api_router


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

# Mount static files for uploads
uploads_path = Path(settings.LOCAL_STORAGE_PATH)
if uploads_path.exists():
    app.mount("/uploads", StaticFiles(directory=str(uploads_path)), name="uploads")

# Include API router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


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
