"""
配置管理模块

从 YAML 配置文件加载配置。
"""

import sys
from pathlib import Path
from typing import Any, Dict

import yaml
from loguru import logger


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """加载配置文件"""
    path = Path(config_path)

    if not path.exists():
        logger.error(f"配置文件不存在: {config_path}")
        logger.info("请复制 config.yaml.example 为 config.yaml 并填入配置")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    _validate_config(config)
    return config


def _validate_config(config: Dict[str, Any]):
    """校验配置完整性"""
    errors = []

    # 检查必要的配置项
    if not config.get("stream", {}).get("live_url"):
        errors.append("stream.live_url 未配置")

    if not config.get("whisper", {}).get("api_key"):
        errors.append("whisper.api_key 未配置")

    if not config.get("summarize", {}).get("api_key"):
        errors.append("summarize.api_key 未配置")

    if not config.get("feishu", {}).get("webhook_url"):
        errors.append("feishu.webhook_url 未配置")

    if errors:
        for e in errors:
            logger.error(f"配置错误: {e}")
        sys.exit(1)


def setup_logging(config: Dict[str, Any]):
    """配置日志"""
    log_config = config.get("logging", {})
    level = log_config.get("level", "INFO")
    log_file = log_config.get("file", "")

    # 移除默认 handler
    logger.remove()

    # 添加控制台输出
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    )

    # 添加文件输出
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_file,
            level=level,
            rotation="10 MB",
            retention="7 days",
            encoding="utf-8",
        )
