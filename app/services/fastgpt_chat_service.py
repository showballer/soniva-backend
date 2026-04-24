"""
FastGPT chat-analysis streaming client.

Calls the FastGPT workflow configured for the taoxi-style 识Ta feature and
yields normalised SSE events suitable for re-broadcasting to the frontend.

Events yielded (as dicts):
  {"type": "node",     "name": str, "status": str}        # workflow node progress
  {"type": "answer",   "delta": str}                       # streaming markdown delta
  {"type": "duration", "seconds": int}                     # total workflow runtime
  {"type": "tactics",  "data": List[{title, description, phrases}]}  # TRIPLE-TACTICS cards
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
    def _parse_strategies(extract: Dict) -> List[Dict]:
        """
        Turn FastGPT `策略生成` extractResult flat keys into a list of tactic
        dicts suitable for the frontend to render as cards.

        Input shape (flat):
            strategy1_title, strategy1_depth, strategy1_reply1..N,
            strategy2_title, strategy2_depth, strategy2_reply1..N,
            ...

        Output shape (list):
            [
              {"title": "...", "description": "...",
               "phrases": ["...", "...", ...]},
              ...
            ]
        """
        tactics: List[Dict] = []
        idx = 1
        while True:
            title = extract.get(f"strategy{idx}_title")
            if not title:
                break
            description = extract.get(f"strategy{idx}_depth", "") or ""
            phrases: List[str] = []
            j = 1
            while True:
                phrase = extract.get(f"strategy{idx}_reply{j}")
                if not phrase:
                    break
                phrases.append(str(phrase))
                j += 1
            tactics.append({
                "title": str(title),
                "description": str(description),
                "phrases": phrases,
            })
            idx += 1
        return tactics

    @staticmethod
    def _build_user_content(
        text: Optional[str],
        image_urls: Optional[List[str]] = None,
    ) -> List[Dict]:
        parts: List[Dict] = []
        if text:
            parts.append({"type": "text", "text": text})
        for url in image_urls or []:
            if url:
                parts.append({"type": "image_url", "image_url": {"url": url}})
        if not parts:
            parts.append({"type": "text", "text": ""})
        return parts

    async def stream_chat(
        self,
        *,
        chat_id: str,
        user_id: str,
        text: Optional[str],
        image_urls: Optional[List[str]] = None,
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
        imgs = [u for u in (image_urls or []) if u]
        payload = {
            "chatId": chat_id,
            "stream": True,
            "detail": True,
            "messages": [
                {
                    "role": "user",
                    "content": self._build_user_content(text, imgs),
                }
            ],
            "customUid": user_id,
        }

        logger.info(
            "FastGPT chat stream start chatId=%s images=%d",
            chat_id,
            len(imgs),
        )

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

        if event_name == "flowResponses":
            # Full dump of every workflow node. We only care about the
            # `策略生成` contentExtract module — its extractResult holds
            # structured TRIPLE-TACTICS cards we can render on the client.
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                return
            if not isinstance(payload, list):
                return
            for module in payload:
                if not isinstance(module, dict):
                    continue
                extract = module.get("extractResult")
                if not isinstance(extract, dict):
                    continue
                # Identify by the strategy1_title key — survives rename of
                # moduleName/nodeId in the FastGPT editor.
                if "strategy1_title" not in extract:
                    continue
                tactics = FastGPTChatService._parse_strategies(extract)
                if tactics:
                    yield {"type": "tactics", "data": tactics}
                break
            return

        # other event types (flowNodeResponse, toolCall, etc): ignored.


fastgpt_chat_service = FastGPTChatService()
