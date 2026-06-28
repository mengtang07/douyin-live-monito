"""
音频捕获模块

支持两种模式：
1. 直播流抓取: 从抖音页面提取流地址，ffmpeg 抓流
2. 系统音频录制: 录制系统音频输出 (需要 BlackHole 虚拟音频设备)
"""

import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import requests
from loguru import logger


class StreamCapture:
    """捕获音频并分片输出"""

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    def __init__(self, live_url: str, chunk_duration: int = 30, mode: str = "auto",
                 audio_device: str = "", sample_rate: int = 16000):
        self.live_url = live_url
        self.chunk_duration = chunk_duration
        self.mode = mode  # "stream", "system_audio", or "auto"
        self.audio_device = audio_device
        self.sample_rate = sample_rate
        self._running = False
        self._process: Optional[subprocess.Popen] = None
        self._on_chunk: Optional[Callable[[str], None]] = None
        self._temp_dir: Optional[str] = None

    def on_chunk(self, callback: Callable[[str], None]):
        """注册音频分片完成的回调函数"""
        self._on_chunk = callback

    def start(self):
        """开始捕获"""
        self._running = True
        self._temp_dir = tempfile.mkdtemp(prefix="douyin_monitor_")
        logger.info(f"音频捕获启动 (模式: {self.mode})")
        logger.info(f"临时目录: {self._temp_dir}")

        thread = threading.Thread(target=self._capture_loop, daemon=True)
        thread.start()

    def stop(self):
        """停止捕获"""
        self._running = False
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._cleanup()
        logger.info("已停止音频捕获")

    def _cleanup(self):
        """清理临时文件"""
        if self._temp_dir and os.path.exists(self._temp_dir):
            try:
                shutil.rmtree(self._temp_dir)
                logger.info(f"已清理临时目录: {self._temp_dir}")
            except Exception as e:
                logger.warning(f"清理临时目录失败: {e}")

    def _capture_loop(self):
        """主捕获循环"""
        if self.mode == "mic":
            self._capture_mic()
        elif self.mode == "system_audio":
            self._capture_system_audio()
        elif self.mode == "stream":
            self._capture_stream()
        else:
            # auto: 先尝试 stream，失败则用麦克风
            if not self._try_stream_once():
                logger.info("流抓取失败，切换到麦克风录音模式")
                self._capture_mic()
            else:
                self._capture_stream()

    # ---- 麦克风录音模式 ----

    def _capture_mic(self):
        """麦克风录音模式"""
        device = self.audio_device or "0"
        self._start_ffmpeg_mic(device)

    def _start_ffmpeg_mic(self, device: str):
        """使用 ffmpeg 从麦克风录音"""
        output_pattern = os.path.join(self._temp_dir, "chunk_%03d.wav")

        ffmpeg_cmd = [
            "ffmpeg",
            "-f", "avfoundation",
            "-i", f":{device}",  # 只捕获音频
            "-f", "segment",
            "-segment_time", str(self.chunk_duration),
            "-ac", "1",
            "-ar", str(self.sample_rate),
            "-acodec", "pcm_s16le",
            output_pattern,
            "-y",
        ]

        logger.info(f"启动麦克风录音 (设备: {device}, 分片: {self.chunk_duration}s)")
        logger.info("请用手机打开直播间并外放声音")
        logger.debug(f"ffmpeg: {' '.join(ffmpeg_cmd)}")

        self._process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self._watch_chunks()

    # ---- 流抓取模式 ----

    @staticmethod
    def _decode_url(url: str) -> str:
        url = url.replace("\\u0026", "&")
        url = url.replace("&amp;", "&")
        return url

    def _fetch_stream_url(self) -> Optional[str]:
        """从抖音页面提取直播流地址"""
        try:
            resp = requests.get(
                self.live_url,
                headers=self.HEADERS,
                cookies={"__ac_nonce": "01234567890123456789"},
                timeout=15,
            )
            content = resp.text

            # 检查是否被验证码拦截
            if "验证码" in content or len(content) < 10000:
                logger.debug("页面被验证码拦截或内容过短")
                return None

            # 检查是否在线
            status_match = re.search(r'"status":(\d+)', content)
            if status_match and int(status_match.group(1)) != 2:
                logger.info("直播间当前不在线")
                return None

            # 提取带签名的完整 FLV URL
            for quality in ["_or4", "_Stage0T000hd", ""]:
                pattern = rf'(https?://pull-flv[^"\'<>\s]+{quality}\.flv\?[^"\'<>\s]*sign=[^"\'<>\s]+)'
                match = re.search(pattern, content)
                if match:
                    url = self._decode_url(match.group(1))
                    logger.info(f"提取到 FLV 流地址")
                    return url

            return None
        except Exception as e:
            logger.error(f"获取流地址失败: {e}")
            return None

    def _try_stream_once(self) -> bool:
        """尝试获取一次流地址，返回是否成功"""
        url = self._fetch_stream_url()
        return url is not None

    def _capture_stream(self):
        """流抓取模式循环"""
        while self._running:
            try:
                stream_url = self._fetch_stream_url()
                if stream_url:
                    self._start_ffmpeg_input(stream_url)
                else:
                    logger.info("未获取到流地址，10秒后重试...")
                    time.sleep(10)
            except Exception as e:
                logger.error(f"捕获异常 (5秒后重试): {e}")
                time.sleep(5)

    # ---- 系统音频录制模式 ----

    def _find_audio_device(self) -> Optional[str]:
        """查找可用的音频输入设备"""
        if self.audio_device:
            return self.audio_device

        try:
            result = subprocess.run(
                ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                capture_output=True, text=True, timeout=10,
            )
            output = result.stderr

            # 查找 BlackHole 或其他虚拟音频设备
            for line in output.split("\n"):
                if "BlackHole" in line or "blackhole" in line:
                    # 提取设备索引
                    match = re.search(r'\[(\d+)\]', line)
                    if match:
                        device = match.group(1)
                        logger.info(f"找到音频设备: {line.strip()}")
                        return device

            # 查找所有音频设备
            devices = []
            for line in output.split("\n"):
                if "AVFoundation audio" in line:
                    continue
                match = re.search(r'\[(\d+)\]\s+(.+)', line)
                if match:
                    devices.append((match.group(1), match.group(2).strip()))

            if devices:
                logger.warning(f"未找到 BlackHole，可用音频设备: {devices}")
                logger.info("提示: 安装 BlackHole: brew install blackhole-2ch")
                logger.info("然后在 系统设置 → 声音 中将输出设为 BlackHole 2ch")

            return None
        except Exception as e:
            logger.error(f"查找音频设备失败: {e}")
            return None

    def _capture_system_audio(self):
        """系统音频录制模式"""
        device = self._find_audio_device()
        if not device:
            logger.error("未找到可用的音频输入设备")
            logger.info("请安装 BlackHole: brew install blackhole-2ch")
            logger.info("安装后需要重启终端，并在 系统设置 → 声音 中配置")
            while self._running:
                time.sleep(5)
            return

        logger.info(f"使用音频设备 [{device}] 录制系统音频")
        self._start_ffmpeg_device(device)

    def _start_ffmpeg_device(self, device: str):
        """使用 ffmpeg 录制系统音频设备"""
        output_pattern = os.path.join(self._temp_dir, "chunk_%03d.wav")

        ffmpeg_cmd = [
            "ffmpeg",
            "-f", "avfoundation",
            "-i", f":{device}",  # 只捕获音频，不捕获视频
            "-f", "segment",
            "-segment_time", str(self.chunk_duration),
            "-ac", "1",
            "-ar", str(self.sample_rate),
            "-acodec", "pcm_s16le",
            output_pattern,
            "-y",
        ]

        logger.info(f"启动系统音频录制 (设备: {device}, 分片: {self.chunk_duration}s)")
        logger.debug(f"ffmpeg: {' '.join(ffmpeg_cmd)}")

        self._process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self._watch_chunks()

    def _start_ffmpeg_input(self, stream_url: str):
        """使用 ffmpeg 处理输入流"""
        output_pattern = os.path.join(self._temp_dir, "chunk_%03d.wav")

        ffmpeg_cmd = [
            "ffmpeg",
            "-i", stream_url,
            "-f", "segment",
            "-segment_time", str(self.chunk_duration),
            "-ac", "1",
            "-ar", str(self.sample_rate),
            "-acodec", "pcm_s16le",
            output_pattern,
            "-y",
        ]

        logger.info("启动 ffmpeg 抓流...")
        self._process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self._watch_chunks()

    def _watch_chunks(self):
        """监控临时目录，发现新音频分片就触发回调"""
        seen = set()
        index = 0

        while self._running:
            time.sleep(1)

            # 检查进程是否还在运行
            if self._process and self._process.poll() is not None:
                stderr = ""
                if self._process.stderr:
                    stderr = self._process.stderr.read().decode(errors="replace")
                logger.warning(f"ffmpeg 退出 (code={self._process.returncode}): {stderr[:300]}")
                break

            expected = os.path.join(self._temp_dir, f"chunk_{index:03d}.wav")

            try:
                if not os.path.exists(expected) or expected in seen:
                    continue
            except OSError:
                continue

            # 等待文件写完 (检查文件大小是否稳定)
            try:
                size1 = os.path.getsize(expected)
                time.sleep(0.5)
                size2 = os.path.getsize(expected)
            except OSError:
                continue

            if size1 == size2 and size2 > 0:
                seen.add(expected)
                logger.info(f"新音频分片: chunk_{index:03d}.wav ({size2} bytes)")
                if self._on_chunk:
                    threading.Thread(
                        target=self._on_chunk,
                        args=(expected,),
                        daemon=True,
                    ).start()
                index += 1
