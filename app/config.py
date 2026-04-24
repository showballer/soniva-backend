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

    # Aliyun OSS (preferred — overrides OSS_* above when provided)
    ALIYUN_ACCESS_KEY_ID: str = ""
    ALIYUN_ACCESS_KEY_SECRET: str = ""
    ALIYUN_OSS_REGION: str = ""       # e.g. oss-cn-shanghai
    ALIYUN_OSS_BUCKET: str = ""       # e.g. showballer-voice

    # FastGPT
    FASTGPT_API_BASE: str = ""
    FASTGPT_API_KEY: str = ""
    FASTGPT_WORKFLOW_VOICE_ANALYSIS: str = ""
    FASTGPT_WORKFLOW_CHAT_ANALYSIS: str = ""
    FASTGPT_WORKFLOW_MOMENTS_ANALYSIS: str = ""
    FASTGPT_WORKFLOW_AVATAR_ANALYSIS: str = ""

    # FastGPT - chat analysis workflow (taoxi-style 识Ta)
    FASTGPT_CHAT_ANALYSIS_URL: str = "https://www.yyshowballer.cn/api/v1/chat/completions"
    FASTGPT_CHAT_ANALYSIS_KEY: str = ""

    # SMS (Aliyun Dysmsapi 2017-05-25)
    SMS_ACCESS_KEY_ID: str = ""
    SMS_ACCESS_KEY_SECRET: str = ""
    SMS_SIGN_NAME: str = ""
    SMS_TEMPLATE_CODE: str = ""
    SMS_ENDPOINT: str = ""  # defaults to dysmsapi.aliyuncs.com when blank

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

    # ---- OSS resolved values (prefer ALIYUN_* when configured) ----
    @property
    def OSS_KEY_ID(self) -> str:
        return self.ALIYUN_ACCESS_KEY_ID or self.OSS_ACCESS_KEY_ID

    @property
    def OSS_KEY_SECRET(self) -> str:
        return self.ALIYUN_ACCESS_KEY_SECRET or self.OSS_ACCESS_KEY_SECRET

    @property
    def OSS_BUCKET(self) -> str:
        return self.ALIYUN_OSS_BUCKET or self.OSS_BUCKET_NAME

    @property
    def OSS_ENDPOINT_URL(self) -> str:
        """Return e.g. https://oss-cn-shanghai.aliyuncs.com"""
        if self.ALIYUN_OSS_REGION:
            return f"https://{self.ALIYUN_OSS_REGION}.aliyuncs.com"
        if self.OSS_ENDPOINT:
            if self.OSS_ENDPOINT.startswith("http"):
                return self.OSS_ENDPOINT
            return f"https://{self.OSS_ENDPOINT}"
        return ""

    @property
    def OSS_PUBLIC_HOST(self) -> str:
        """Return e.g. https://bucket.oss-cn-shanghai.aliyuncs.com"""
        if self.OSS_CDN_URL:
            return self.OSS_CDN_URL.rstrip("/")
        if self.ALIYUN_OSS_REGION and self.OSS_BUCKET:
            return f"https://{self.OSS_BUCKET}.{self.ALIYUN_OSS_REGION}.aliyuncs.com"
        if self.OSS_ENDPOINT and self.OSS_BUCKET:
            host = self.OSS_ENDPOINT.replace("https://", "").replace("http://", "").rstrip("/")
            return f"https://{self.OSS_BUCKET}.{host}"
        return ""

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
