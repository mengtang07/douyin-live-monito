"""
飞书消息推送模块

通过飞书自定义机器人 Webhook 发送消息。
"""

import base64
import hashlib
import hmac
import json
import time
from typing import Optional

import requests
from loguru import logger


class FeishuNotifier:
    """飞书 Webhook 消息推送"""

    WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/"

    def __init__(self, webhook_url: str, secret: str = ""):
        self.webhook_url = webhook_url
        self.secret = secret

    def _gen_sign(self) -> dict:
        """生成签名 (如果配置了签名密钥)"""
        if not self.secret:
            return {}

        timestamp = str(int(time.time()))
        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(
            self.secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = base64.b64encode(hmac_code).decode("utf-8")

        return {"timestamp": timestamp, "sign": sign}

    def send_text(self, text: str) -> bool:
        """发送纯文本消息"""
        payload = {
            "msg_type": "text",
            "content": {"text": text},
        }
        payload.update(self._gen_sign())
        return self._send(payload)

    def send_summary(self, title: str, content: str, is_final: bool = False) -> bool:
        """
        发送格式化的总结消息 (富文本卡片)

        Args:
            title: 消息标题
            content: 总结内容 (Markdown 格式)
            is_final: 是否为最终总结
        """
        # 使用飞书的交互式卡片消息
        emoji = "📋" if is_final else "📝"
        color = "green" if is_final else "blue"

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"{emoji} {title}",
                },
                "template": color,
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": content,
                },
                {
                    "tag": "hr",
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": f"🤖 由直播监控智能体自动生成 | {time.strftime('%Y-%m-%d %H:%M:%S')}",
                        }
                    ],
                },
            ],
        }

        payload = {
            "msg_type": "interactive",
            "card": card,
        }
        payload.update(self._gen_sign())
        return self._send(payload)

    def _send(self, payload: dict) -> bool:
        """发送消息到飞书"""
        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )

            result = response.json()

            if result.get("code") == 0 or result.get("StatusCode") == 0:
                logger.info("飞书消息发送成功")
                return True
            else:
                logger.error(f"飞书消息发送失败: {result}")
                return False

        except Exception as e:
            logger.error(f"飞书消息发送异常: {e}")
            return False
