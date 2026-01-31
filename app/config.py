"""
Soniva Backend Configuration
"""
from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Soniva"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # File Storage
    STORAGE_TYPE: str = "local"
    LOCAL_STORAGE_PATH: str = "./uploads"
    OSS_ACCESS_KEY_ID: str = ""
    OSS_ACCESS_KEY_SECRET: str = ""
    OSS_BUCKET_NAME: str = ""
    OSS_ENDPOINT: str = ""
    OSS_CDN_URL: str = ""

    # FastGPT
    FASTGPT_API_BASE: str = ""
    FASTGPT_API_KEY: str = ""
    FASTGPT_WORKFLOW_VOICE_ANALYSIS: str = ""
    FASTGPT_WORKFLOW_CHAT_ANALYSIS: str = ""
    FASTGPT_WORKFLOW_MOMENTS_ANALYSIS: str = ""
    FASTGPT_WORKFLOW_AVATAR_ANALYSIS: str = ""

    # SMS
    SMS_ACCESS_KEY_ID: str = ""
    SMS_ACCESS_KEY_SECRET: str = ""
    SMS_SIGN_NAME: str = ""
    SMS_TEMPLATE_CODE: str = ""

    # CORS
    CORS_ORIGINS_STR: str = '["*"]'

    # App URL
    APP_BASE_URL: str = "http://localhost:8000"

    # Log
    LOG_LEVEL: str = "INFO"

    @property
    def CORS_ORIGINS(self) -> List[str]:
        try:
            return json.loads(self.CORS_ORIGINS_STR)
        except:
            return ["*"]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
