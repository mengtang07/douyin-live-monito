"""
直播监控智能体 - 主控制器

协调音频捕获、语音识别、内容总结、飞书推送的完整流程。
"""

import signal
import sys
import threading
import time
from typing import List

from loguru import logger

from .config import load_config, setup_logging
from .capture import StreamCapture
from .transcribe import WhisperTranscriber
from .summarize import GPTSummarizer
from .notify import FeishuNotifier


class LiveMonitor:
    """抖音直播监控智能体主控制器"""

    def __init__(self, config_path: str = "config.yaml"):
        self.config = load_config(config_path)
        setup_logging(self.config)

        stream_cfg = self.config["stream"]
        whisper_cfg = self.config["whisper"]
        summarize_cfg = self.config["summarize"]
        feishu_cfg = self.config["feishu"]

        self.capture = StreamCapture(
            live_url=stream_cfg["live_url"],
            chunk_duration=stream_cfg.get("chunk_duration", 30),
            mode=stream_cfg.get("mode", "auto"),
            audio_device=stream_cfg.get("audio_device", ""),
        )

        self.transcriber = WhisperTranscriber(
            api_key=whisper_cfg["api_key"],
            base_url=whisper_cfg.get("base_url", ""),
            model=whisper_cfg.get("model", "whisper-1"),
            language=whisper_cfg.get("language", "zh"),
        )

        self.summarizer = GPTSummarizer(
            api_key=summarize_cfg["api_key"],
            base_url=summarize_cfg.get("base_url", ""),
            model=summarize_cfg.get("model", "gpt-4o-mini"),
        )

        self.notifier = FeishuNotifier(
            webhook_url=feishu_cfg["webhook_url"],
            secret=feishu_cfg.get("secret", ""),
        )

        self.summary_interval = summarize_cfg.get("interval", 600)
        self.enable_final_summary = summarize_cfg.get("final_summary", True)

        self._transcript_buffer: List[str] = []
        self._all_transcripts: List[str] = []
        self._buffer_lock = threading.Lock()
        self._start_time: float = 0
        self._running = False
        self._summary_count: int = 0

        self.capture.on_chunk(self._on_audio_chunk)

    def start(self):
        """启动监控"""
        mode = self.config['stream'].get('mode', 'auto')
        logger.info("=" * 50)
        logger.info("抖音直播监控智能体启动")
        if mode == "mic":
            logger.info("模式: 麦克风录音 (请用手机打开直播间并外放)")
        elif mode == "system_audio":
            logger.info("模式: 系统音频录制")
        else:
            logger.info(f"模式: 直播流抓取 | 地址: {self.config['stream']['live_url']}")
        logger.info(f"总结间隔: {self.summary_interval}秒")
        logger.info("输入 q + 回车 可随时结束并生成总结")
        logger.info("=" * 50)

        self._running = True
        self._start_time = time.time()

        self.notifier.send_text("[启动] 直播监控已启动，正在监听直播内容...")
        self.capture.start()

        summary_thread = threading.Thread(target=self._summary_loop, daemon=True)
        summary_thread.start()

        # 监听键盘输入，输入 q 结束
        input_thread = threading.Thread(target=self._listen_input, daemon=True)
        input_thread.start()

        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        """停止监控"""
        if not self._running:
            return

        logger.info("正在停止监控...")
        self._running = False
        self.capture.stop()

        if self.enable_final_summary and self._all_transcripts:
            logger.info("生成最终总结...")
            self._do_final_summary()

        duration = int(time.time() - self._start_time)
        minutes = duration // 60
        self.notifier.send_text(
            f"[停止] 直播监控已停止 | 时长: {minutes}分钟 | 片段: {len(self._all_transcripts)}条"
        )
        logger.info("监控已完全停止")

    def _on_audio_chunk(self, audio_path: str):
        """处理新的音频分片"""
        text = self.transcriber.transcribe(audio_path)
        if text:
            with self._buffer_lock:
                self._transcript_buffer.append(text)
                self._all_transcripts.append(text)

    def _summary_loop(self):
        """定时总结循环"""
        while self._running:
            time.sleep(self.summary_interval)
            if not self._running:
                break

            with self._buffer_lock:
                if not self._transcript_buffer:
                    continue
                texts = self._transcript_buffer.copy()
                self._transcript_buffer.clear()

            combined_text = "\n".join(texts)
            self._summary_count += 1

            summary = self.summarizer.summarize_interval(combined_text)
            if summary:
                now = time.strftime("%H:%M")
                title = f"直播阶段性总结 (第{self._summary_count}次·{now})"
                self.notifier.send_summary(title, summary, is_final=False)
                logger.info(f"阶段性总结已推送: {title}")

    def _do_final_summary(self):
        """生成并发送最终总结"""
        combined_text = "\n".join(self._all_transcripts)

        max_chars = 50000
        if len(combined_text) > max_chars:
            combined_text = combined_text[-max_chars:]
            logger.warning(f"转录文本过长，截取最后{max_chars}字符")

        summary = self.summarizer.summarize_final(combined_text)
        if summary:
            elapsed = int(time.time() - self._start_time)
            minutes = elapsed // 60
            title = f"直播完整总结报告 (总时长{minutes}分钟)"
            self.notifier.send_summary(title, summary, is_final=True)
            logger.info("最终总结已推送")

    def _listen_input(self):
        """监听键盘输入，输入 q 结束监控"""
        while self._running:
            try:
                cmd = input().strip().lower()
                if cmd == "q":
                    logger.info("收到手动结束指令")
                    self.stop()
                    break
            except EOFError:
                break
            except Exception:
                pass

    def _handle_shutdown(self, signum, frame):
        logger.info(f"收到信号{signum}，准备关闭...")
        self.stop()
        sys.exit(0)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="抖音直播监控智能体")
    parser.add_argument("-c", "--config", default="config.yaml", help="配置文件路径")
    args = parser.parse_args()

    monitor = LiveMonitor(config_path=args.config)
    monitor.start()
