"""
GPT 内容总结模块

使用 OpenAI GPT 模型对直播转录文本进行智能总结。
"""

import time
from typing import Optional

from loguru import logger
from openai import OpenAI


class GPTSummarizer:
    """使用 GPT 模型总结直播内容"""

    MAX_RETRIES = 3

    INTERVAL_PROMPT = """你是一个专业的直播内容分析师。请根据以下直播转录文本，生成一份简洁的阶段性总结。

要求：
1. 提炼主播的核心观点和关键信息
2. 如果涉及产品/商品，列出名称、价格、优惠信息
3. 如果有互动亮点（如抽奖、连麦），单独标注
4. 使用清晰的结构化格式输出
5. 控制在200字以内

直播转录文本：
{text}"""

    FINAL_PROMPT = """你是一个专业的直播内容分析师。请根据以下整场直播的转录文本，生成一份完整的直播总结报告。

要求：
1. 直播主题和核心内容概述
2. 主要讨论的要点（按时间线或主题分类）
3. 涉及的产品/商品信息汇总（名称、价格、优惠）
4. 观众互动亮点
5. 关键金句或重要声明
6. 整体评价和要点提炼
7. 使用清晰的结构化格式

直播转录文本：
{text}"""

    def __init__(self, api_key: str, base_url: str = "", model: str = "gpt-4o-mini"):
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)
        self.model = model

    def summarize_interval(self, text: str) -> Optional[str]:
        """生成阶段性总结"""
        return self._call_gpt(self.INTERVAL_PROMPT.format(text=text))

    def summarize_final(self, text: str) -> Optional[str]:
        """生成完整总结"""
        return self._call_gpt(self.FINAL_PROMPT.format(text=text))

    def _call_gpt(self, prompt: str) -> Optional[str]:
        """调用 GPT API (带重试)"""
        logger.info(f"调用 GPT 总结 (prompt 长度: {len(prompt)} chars)")

        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "你是一个专业的直播内容分析师，擅长提炼关键信息并生成结构化总结。",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_tokens=1000,
                )

                result = response.choices[0].message.content.strip()
                logger.info(f"总结完成 ({len(result)} chars)")
                return result

            except Exception as e:
                wait = 2 ** attempt
                logger.warning(f"GPT 总结失败 (第{attempt+1}次, {wait}s后重试): {e}")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(wait)

        logger.error("GPT 总结最终失败")
        return None
