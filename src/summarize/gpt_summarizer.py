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

    INTERVAL_PROMPT = """你是一个专业的财经直播内容分析师。请根据以下财经主播的直播转录文本，生成一份简洁的阶段性总结。

要求：
1. **市场观点**: 提炼主播对大盘/板块的核心判断（看多/看空/震荡）
2. **个股分析**: 涉及的股票名称、代码、关键价位、操作建议
3. **板块动向**: 提到的热点板块、行业趋势、资金流向
4. **技术指标**: 提及的K线形态、均线、量能、MACD等技术分析要点
5. **风险提示**: 主播提到的风险点、注意事项、止损位
6. **关键原话**: 记录主播的重要判断原话（用引号标注）
7. 控制在300字以内，使用结构化格式

直播转录文本：
{text}"""

    FINAL_PROMPT = """你是一个专业的财经直播内容分析师。请根据以下整场财经直播的转录文本，生成一份完整的直播总结报告。

要求：
1. **直播概述**: 主播身份、直播主题、核心立场
2. **大盘研判**: 对A股/美股/港股等的整体观点和逻辑
3. **个股推荐**: 涉及的所有股票（名称、代码、目标价、操作建议、逻辑）
4. **板块分析**: 看好/看空的板块及原因
5. **技术分析**: 关键技术位、形态判断、量价关系
6. **操作策略**: 建议的仓位、买卖时机、止损止盈位
7. **风险提示**: 主播强调的风险和注意事项
8. **金句摘录**: 重要的判断和观点原话
9. **整体评价**: 主播观点的逻辑性和参考价值

请使用清晰的结构化格式输出。

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
                            "content": "你是一个资深的财经直播分析师，擅长从直播内容中提取股票、板块、技术分析、操作策略等关键财经信息，生成专业、结构化的总结报告。",
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
