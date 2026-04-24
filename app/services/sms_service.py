"""
Aliyun SMS service wrapper.

Wraps Dysmsapi 2017-05-25 (Python Tea SDK). Used by /auth/send-code to deliver
phone verification codes to end users.

Required env vars:
    SMS_ACCESS_KEY_ID       - Aliyun AccessKey (can reuse ALIYUN_ACCESS_KEY_ID)
    SMS_ACCESS_KEY_SECRET   - Aliyun AccessKey secret
    SMS_SIGN_NAME           - SMS signature configured in Aliyun console
    SMS_TEMPLATE_CODE       - SMS template code, e.g. SMS_123456789
    SMS_ENDPOINT (optional) - defaults to dysmsapi.aliyuncs.com

The template must contain a `${code}` placeholder; we pass `{"code": "xxxxxx"}`
as template_param.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from alibabacloud_dysmsapi20170525.client import Client as DysmsapiClient
from alibabacloud_dysmsapi20170525 import models as dysmsapi_models
from alibabacloud_tea_openapi import models as open_api_models

from app.config import settings

logger = logging.getLogger(__name__)


class SmsResult:
    __slots__ = ("success", "code", "message", "request_id", "biz_id")

    def __init__(
        self,
        success: bool,
        code: str = "",
        message: str = "",
        request_id: Optional[str] = None,
        biz_id: Optional[str] = None,
    ):
        self.success = success
        self.code = code
        self.message = message
        self.request_id = request_id
        self.biz_id = biz_id

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "code": self.code,
            "message": self.message,
            "request_id": self.request_id,
            "biz_id": self.biz_id,
        }


class SmsService:
    """Singleton-style wrapper around the Aliyun Dysmsapi client."""

    _client: Optional[DysmsapiClient] = None

    @classmethod
    def is_configured(cls) -> bool:
        """True iff we have enough env to actually send an SMS."""
        return bool(
            settings.SMS_ACCESS_KEY_ID
            and settings.SMS_ACCESS_KEY_SECRET
            and settings.SMS_SIGN_NAME
            and settings.SMS_TEMPLATE_CODE
        )

    @classmethod
    def _get_client(cls) -> DysmsapiClient:
        if cls._client is None:
            config = open_api_models.Config(
                access_key_id=settings.SMS_ACCESS_KEY_ID,
                access_key_secret=settings.SMS_ACCESS_KEY_SECRET,
                endpoint=settings.SMS_ENDPOINT or "dysmsapi.aliyuncs.com",
            )
            cls._client = DysmsapiClient(config)
        return cls._client

    @classmethod
    def send_verification_code(cls, phone: str, code: str) -> SmsResult:
        """
        Send a 6-digit verification code to `phone`.

        Returns an SmsResult. On non-OK Aliyun response we populate
        `code`/`message` from the response body so the caller can surface them.
        """
        if not cls.is_configured():
            return SmsResult(
                success=False,
                code="SMS_NOT_CONFIGURED",
                message="SMS service is not configured",
            )

        req = dysmsapi_models.SendSmsRequest(
            phone_numbers=phone,
            sign_name=settings.SMS_SIGN_NAME,
            template_code=settings.SMS_TEMPLATE_CODE,
            template_param=json.dumps({"code": code}, ensure_ascii=False),
        )

        try:
            resp = cls._get_client().send_sms(req)
        except Exception as e:
            logger.exception("Aliyun SendSms transport error: %s", e)
            return SmsResult(
                success=False,
                code="TRANSPORT_ERROR",
                message=str(e),
            )

        body = resp.body
        resp_code = getattr(body, "code", "") or ""
        resp_msg = getattr(body, "message", "") or ""
        request_id = getattr(body, "request_id", None)
        biz_id = getattr(body, "biz_id", None)

        if resp_code == "OK":
            return SmsResult(
                success=True,
                code=resp_code,
                message=resp_msg or "OK",
                request_id=request_id,
                biz_id=biz_id,
            )

        logger.warning(
            "Aliyun SendSms rejected: code=%s msg=%s request_id=%s",
            resp_code, resp_msg, request_id,
        )
        return SmsResult(
            success=False,
            code=resp_code or "UNKNOWN",
            message=resp_msg or "Aliyun SMS rejected the request",
            request_id=request_id,
            biz_id=biz_id,
        )


sms_service = SmsService()
