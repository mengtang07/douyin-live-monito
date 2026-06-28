#!/usr/bin/env python3
"""抖音直播监控智能体 - 启动脚本"""
import argparse

from src.main import main


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="抖音直播监控智能体")
    parser.add_argument("-c", "--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--web", action="store_true", help="启动 Web 控制面板")
    parser.add_argument("--port", type=int, default=5000, help="Web 端口 (默认 5000)")
    args = parser.parse_args()

    if args.web:
        from src.web.app import run_web
        run_web(port=args.port, config_path=args.config)
    else:
        main()
