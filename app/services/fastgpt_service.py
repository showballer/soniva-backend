"""
FastGPT Service - AI Analysis Integration
"""
import httpx
import json
import logging
from typing import Dict, Any, Optional
from app.config import settings

logger = logging.getLogger(__name__)


class FastGPTService:
    """
    FastGPT API Service for AI-powered analysis
    """

    def __init__(self):
        self.api_url = settings.FASTGPT_API_BASE
        self.api_key = settings.FASTGPT_API_KEY
        # FastGPT 的声鉴 workflow 在多 LLM 调用 + 模型偶尔抽风时可能要
        # 拖到 5 分钟以上，所以给到 10 分钟。worker 是 detached
        # background task，没有客户端 deadline，多等不要紧。
        self.timeout = 600.0
        # 仅对真正的 *瞬时* 错误（5xx、连接失败）重试，不对超时重试 ——
        # 一次超时已经拖了 10 分钟，再来一次大概率还是 10 分钟没结果，
        # 纯放大问题。
        self.max_retries = 1

    async def analyze_voice(
        self,
        voice_features: Dict[str, Any],
        gender: str = "",
        nickname: str = "用户"
    ) -> Optional[Dict[str, Any]]:
        """
        Call FastGPT to analyze voice features and generate insights.

        Returns:
            * `dict` — successful AI response (parsed)
            * `None` — call failed (timeout / network / non-200). Caller
              MUST treat this as failure — never silently fall back to
              hard-coded data, that turned a real outage into "voice
              analysis claims to succeed but every result is identical".

        `gender` is now deprecated and unused.
        """
        if not self.api_key:
            logger.warning("No API key configured, skipping AI analysis")
            return None

        message_content = json.dumps({
            "voice_features": voice_features
        }, ensure_ascii=False)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "chatId": f"voice_analysis_{gender}",
            "stream": False,
            "detail": False,
            "messages": [
                {
                    "role": "user",
                    "content": message_content
                }
            ]
        }

        logger.info("=== FastGPT 请求开始 ===")
        logger.info("请求地址: %s", self.api_url)
        logger.info("请求入参:\n%s", json.dumps(payload, ensure_ascii=False, indent=2))

        # max_retries 次重试 → 总尝试次数 = max_retries + 1
        last_error: Optional[str] = None
        for attempt in range(1, self.max_retries + 2):
            label = f"attempt {attempt}/{self.max_retries + 1}"
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        self.api_url,
                        headers=headers,
                        json=payload,
                    )

                    # === FastGPT 接口返回 (raw HTTP response) ===
                    logger.info("=== FastGPT 接口返回开始 (%s) ===", label)
                    logger.info("响应状态码: %s", response.status_code)
                    logger.info("响应 headers: %s", dict(response.headers))
                    logger.info("响应原始内容 (raw body):\n%s", response.text)
                    logger.info("=== FastGPT 接口返回结束 ===")

                    if response.status_code != 200:
                        last_error = (
                            f"HTTP {response.status_code}: "
                            f"{response.text[:300]}"
                        )
                        logger.error("API 返回错误 (%s): %s", label, last_error)
                        # 4xx 通常是参数/鉴权问题，重试也没用；只对 5xx 重试
                        if 400 <= response.status_code < 500:
                            return None
                        continue  # retry on 5xx

                    result = response.json()
                    choices = result.get("choices") or []
                    if not choices:
                        last_error = "FastGPT 返回 choices 为空"
                        logger.error("%s (%s)", last_error, label)
                        continue

                    content = (choices[0].get("message") or {}).get("content", "")
                    logger.info(
                        "AI 返回 content (choices[0].message.content):\n%s",
                        content,
                    )

                    parsed = self._parse_voice_analysis_response(content)
                    if not parsed:
                        last_error = "FastGPT 返回的 content 解析失败或字段为空"
                        logger.error("%s (%s)", last_error, label)
                        # 解析失败大概率是 prompt/模型问题，重试也是这个结果
                        return None

                    logger.info(
                        "解析后结果 (parsed dict):\n%s",
                        json.dumps(parsed, ensure_ascii=False, indent=2),
                    )
                    logger.info("=== FastGPT 请求结束 ===")
                    return parsed

            except httpx.TimeoutException:
                last_error = f"请求超时 (timeout={self.timeout:.0f}s)"
                logger.error("%s (%s)", last_error, label)
                # 超时已经拖了 10 分钟，再 retry 一次大概率还是同样结果，
                # 直接放弃。
                return None
            except (httpx.ConnectError, httpx.NetworkError) as exc:
                last_error = f"网络错误: {exc}"
                logger.error("%s (%s)", last_error, label)
                # 真正的瞬时错误，值得 retry。
                continue
            except Exception as exc:  # noqa: BLE001
                last_error = f"FastGPT 调用异常: {exc}"
                logger.exception("%s (%s)", last_error, label)
                # 未知异常不重试，避免把奇怪状态放大
                return None

        logger.error("FastGPT 重试用尽，最终失败: %s", last_error)
        return None

    def _parse_voice_analysis_response(self, content: str) -> Dict[str, Any]:
        """
        解析 FastGPT 返回的新格式数据
        返回格式：
        {
          "gender": "女",
          "main_voice_type": {
            "level1": "少女音",
            "level2": "软妹少女音",
            "full_name": "小家碧玉软妹少女音"
          },
          "auxiliary_tags": ["气息感", "绒感", "温暖", "电台适配"],
          "development_directions": ["少御音", "甜美音"],
          "voice_position": "发声于中央喉位",
          "resonance": ["胸腔", "鼻腔"],
          "voice_attribute": "受",
          "voice_temperature": "暖",
          "perceived_food": "蜂蜜柚子茶配芝士蛋糕",
          "perceived_age": 20,
          "perceived_height": 164,
          "perceived_feedback": ["甜到心坎", "软萌可爱", "想rua"],
          "love_score": 85,
          "recommended_partner": ["青年", "温柔奶狗"],
          "signature": "月落星河入梦来，声如暖玉化春风。",
          "improvement_tips": [
            "可尝试在发声时增加一些气息变化，让声音更加灵动",
            "录音时可选择更安静的环境以充分展现声音质感"
          ],
          "recommended_songs": ["小幸运", "恋爱ING", "喜欢你"]
        }
        """
        try:
            # Clean up the content - remove markdown code blocks if present
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            # Parse JSON
            data = json.loads(content)

            # 直接返回解析后的数据，字段名保持一致
            return {
                "gender": data.get("gender", ""),
                "main_voice_type": data.get("main_voice_type", {}),
                "auxiliary_tags": data.get("auxiliary_tags", []),
                "development_directions": data.get("development_directions", []),
                "voice_position": data.get("voice_position", ""),
                "resonance": data.get("resonance", []),
                "voice_attribute": data.get("voice_attribute", ""),
                "voice_temperature": data.get("voice_temperature", ""),
                "perceived_food": data.get("perceived_food", ""),
                "perceived_age": data.get("perceived_age", 0),
                "perceived_height": data.get("perceived_height", 0),
                "perceived_feedback": data.get("perceived_feedback", []),
                "love_score": data.get("love_score", 0),
                "recommended_partner": data.get("recommended_partner", []),
                "signature": data.get("signature", ""),
                "improvement_tips": data.get("improvement_tips", []),
                "recommended_songs": data.get("recommended_songs", []),
            }

        except json.JSONDecodeError as e:
            logger.error("JSON 解析失败: %s", e)
            logger.error("原始内容:\n%s", content)
            return {}
        except Exception as e:
            logger.exception("解析响应异常: %s", e)
            return {}



# Singleton instance
fastgpt_service = FastGPTService()
