"""
语音识别模块

支持两种模式:
1. OpenAI Whisper API (/audio/transcriptions)
2. 小米等兼容 API (通过 chat completions + input_audio)
"""

import base64
import os
import time
from pathlib import Path
from typing import Optional

from loguru import logger
from openai import OpenAI


class WhisperTranscriber:
    """语音识别"""

    MAX_RETRIES = 3
    # 小米等 ASR 模型使用 chat completions + input_audio 格式
    ASR_MODELS = ["mimo-v2.5-asr", "mimo-asr"]

    def __init__(self, api_key: str, base_url: str = "", model: str = "whisper-1", language: str = "zh"):
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)
        self.model = model
        self.language = language
        self._use_chat_asr = any(m in model for m in self.ASR_MODELS)

    def transcribe(self, audio_path: str) -> Optional[str]:
        """将音频文件转为文字"""
        file_size = os.path.getsize(audio_path)
        if file_size < 1000:
            logger.debug(f"跳过过小的音频文件: {audio_path}")
            return None

        logger.info(f"开始识别: {Path(audio_path).name} ({file_size} bytes)")

        for attempt in range(self.MAX_RETRIES):
            try:
                if self._use_chat_asr:
                    text = self._transcribe_via_chat(audio_path)
                else:
                    text = self._transcribe_via_whisper(audio_path)

                if text:
                    logger.info(f"识别结果: {text[:100]}...")
                else:
                    logger.debug("识别结果为空")

                return text if text else None

            except Exception as e:
                wait = 2 ** attempt
                logger.warning(f"语音识别失败 (第{attempt+1}次, {wait}s后重试): {e}")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(wait)

        logger.error(f"语音识别最终失败: {audio_path}")
        return None

    def _transcribe_via_whisper(self, audio_path: str) -> Optional[str]:
        """通过 OpenAI Whisper API 识别"""
        with open(audio_path, "rb") as f:
            kwargs = {
                "model": self.model,
                "file": f,
                "response_format": "text",
            }
            if self.language:
                kwargs["language"] = self.language
            response = self.client.audio.transcriptions.create(**kwargs)

        text = response.strip() if isinstance(response, str) else response.text.strip()
        return text if text else None

    def _transcribe_via_chat(self, audio_path: str) -> Optional[str]:
        """通过 chat completions + input_audio 识别 (小米等 ASR 模型)"""
        with open(audio_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode()

        # ASR 模型要求消息中只包含 audio，不能有 text
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "input_audio", "input_audio": {"data": audio_b64, "format": "wav"}}
                ]
            }],
            max_tokens=1000,
        )

        text = response.choices[0].message.content.strip()
        return text if text else None
