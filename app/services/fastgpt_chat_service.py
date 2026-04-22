"""
FastGPT chat-analysis streaming client.

Calls the FastGPT workflow configured for the taoxi-style 识Ta feature and
yields normalised SSE events suitable for re-broadcasting to the frontend.

Events yielded (as dicts):
  {"type": "node",     "name": str, "status": str}        # workflow node progress
  {"type": "answer",   "delta": str}                       # streaming markdown delta
  {"type": "duration", "seconds": int}                     # total workflow runtime
  {"type": "done"}                                         # stream finished ok
  {"type": "error",    "message": str}                     # any fatal error
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator, Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class FastGPTChatService:
    def __init__(self) -> None:
        self.url = settings.FASTGPT_CHAT_ANALYSIS_URL
        self.api_key = settings.FASTGPT_CHAT_ANALYSIS_KEY
        self.timeout = httpx.Timeout(
            connect=15.0,
            read=180.0,  # the workflow can take well over a minute
            write=30.0,
            pool=15.0,
        )

    def is_configured(self) -> bool:
        return bool(self.url and self.api_key)

    @staticmethod
    def _build_user_content(text: Optional[str], image_url: Optional[str]) -> List[Dict]:
        parts: List[Dict] = []
        if text:
            parts.append({"type": "text", "text": text})
        if image_url:
            parts.append({"type": "image_url", "image_url": {"url": image_url}})
        if not parts:
            parts.append({"type": "text", "text": ""})
        return parts

    async def stream_chat(
        self,
        *,
        chat_id: str,
        user_id: str,
        text: Optional[str],
        image_url: Optional[str],
    ) -> AsyncIterator[Dict]:
        if not self.is_configured():
            yield {
                "type": "error",
                "message": "FastGPT chat analysis is not configured (FASTGPT_CHAT_ANALYSIS_KEY).",
            }
            return

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        payload = {
            "chatId": chat_id,
            "stream": True,
            "detail": True,
            "messages": [
                {
                    "role": "user",
                    "content": self._build_user_content(text, image_url),
                }
            ],
            "customUid": user_id,
        }

        logger.info("FastGPT chat stream start chatId=%s image=%s", chat_id, bool(image_url))

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", self.url, headers=headers, json=payload) as resp:
                    if resp.status_code != 200:
                        body = (await resp.aread()).decode("utf-8", errors="ignore")
                        logger.error("FastGPT HTTP %s: %s", resp.status_code, body[:500])
                        yield {
                            "type": "error",
                            "message": f"FastGPT returned HTTP {resp.status_code}",
                        }
                        return

                    async for event in self._parse_sse(resp.aiter_lines()):
                        yield event

            yield {"type": "done"}

        except httpx.TimeoutException:
            logger.exception("FastGPT stream timeout")
            yield {"type": "error", "message": "AI 分析超时，请稍后再试"}
        except Exception as exc:  # noqa: BLE001
            logger.exception("FastGPT stream failed")
            yield {"type": "error", "message": f"AI 分析失败: {exc}"}

    # ------------------------------------------------------------------
    # SSE parsing
    # ------------------------------------------------------------------
    @classmethod
    async def _parse_sse(cls, lines: AsyncIterator[str]) -> AsyncIterator[Dict]:
        event_name: Optional[str] = None
        data_buffer: List[str] = []

        async for raw in lines:
            line = raw.rstrip("\r")

            if line == "":
                # dispatch
                if event_name is not None and data_buffer:
                    data_str = "\n".join(data_buffer)
                    for out in cls._translate_event(event_name, data_str):
                        yield out
                event_name = None
                data_buffer = []
                continue

            if line.startswith(":"):
                continue  # SSE comment / keepalive

            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_buffer.append(line[5:].lstrip())

        # trailing event (if server didn't close with blank line)
        if event_name is not None and data_buffer:
            data_str = "\n".join(data_buffer)
            for out in cls._translate_event(event_name, data_str):
                yield out

    @staticmethod
    def _translate_event(event_name: str, data: str):
        data = data.strip()
        if not data:
            return

        if event_name == "answer":
            if data == "[DONE]":
                return
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                return
            choices = payload.get("choices") or []
            if not choices:
                return
            delta = (choices[0].get("delta") or {}).get("content")
            if delta:
                yield {"type": "answer", "delta": delta}
            return

        if event_name == "flowNodeStatus":
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                return
            name = payload.get("name") or ""
            status = payload.get("status") or "running"
            if name:
                yield {"type": "node", "name": name, "status": status}
            return

        if event_name == "workflowDuration":
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                return
            seconds = payload.get("durationSeconds")
            if isinstance(seconds, (int, float)):
                yield {"type": "duration", "seconds": int(seconds)}
            return

        # flowResponses and others: ignore (we don't re-broadcast the full node dump).


fastgpt_chat_service = FastGPTChatService()
