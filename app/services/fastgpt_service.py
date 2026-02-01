"""
FastGPT Service - AI Analysis Integration
"""
import httpx
import json
from typing import Dict, Any, Optional
from app.config import settings


class FastGPTService:
    """
    FastGPT API Service for AI-powered analysis
    """

    def __init__(self):
        self.api_url = "https://cloud.fastgpt.cn/api/v1/chat/completions"
        self.api_key = settings.FASTGPT_API_KEY
        self.timeout = 60.0  # 60 seconds timeout

    async def analyze_voice(
        self,
        voice_features: Dict[str, Any],
        gender: str,
        nickname: str = "用户"
    ) -> Dict[str, Any]:
        """
        Call FastGPT to analyze voice features and generate insights

        Args:
            voice_features: Extracted voice features from librosa
            gender: User's gender (female/male)
            nickname: User's nickname

        Returns:
            AI-generated analysis results
        """
        if not self.api_key:
            print("[FastGPT] No API key configured, skipping AI analysis")
            return {}

        # Send voice features directly as the message content
        # FastGPT workflow will handle the analysis
        message_content = json.dumps({
            "nickname": nickname,
            "gender": "女" if gender == "female" else "男",
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

        try:
            print(f"[FastGPT] Calling API for voice analysis...")
            print(f"[FastGPT] Request URL: {self.api_url}")
            print(f"[FastGPT] Request payload: {json.dumps(payload, ensure_ascii=False, indent=2)}")

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.api_url,
                    headers=headers,
                    json=payload
                )

                print(f"[FastGPT] Response status: {response.status_code}")
                print(f"[FastGPT] Response body: {response.text}")

                if response.status_code == 200:
                    result = response.json()
                    # Extract the content from the response
                    if "choices" in result and len(result["choices"]) > 0:
                        content = result["choices"][0].get("message", {}).get("content", "")
                        print(f"[FastGPT] AI Response content: {content}")

                        # Parse the response in the expected format
                        parsed_result = self._parse_voice_analysis_response(content)
                        print(f"[FastGPT] Parsed result: {json.dumps(parsed_result, ensure_ascii=False, indent=2)}")
                        return parsed_result
                else:
                    print(f"[FastGPT] API error: {response.status_code} - {response.text}")
                    return {}

        except httpx.TimeoutException:
            print(f"[FastGPT] Request timeout after {self.timeout}s")
            return {}
        except Exception as e:
            print(f"[FastGPT] Error calling API: {str(e)}")
            return {}

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
            print(f"[FastGPT] Failed to parse JSON: {e}")
            print(f"[FastGPT] Raw content: {content}")
            return {}
        except Exception as e:
            print(f"[FastGPT] Error parsing response: {e}")
            return {}



# Singleton instance
fastgpt_service = FastGPTService()
