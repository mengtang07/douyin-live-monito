"""
Web 控制面板

通过浏览器控制直播监控的开始/结束。
"""

import threading
import time

from flask import Flask, jsonify, render_template, request
from loguru import logger

from ..main import LiveMonitor

app = Flask(__name__, template_folder="templates")

# 全局状态
_monitor: LiveMonitor = None
_monitor_thread: threading.Thread = None
_status = {
    "running": False,
    "start_time": 0,
    "summary_count": 0,
    "transcript_count": 0,
    "logs": [],  # 最近日志
}
_status_lock = threading.Lock()


def _log_callback(msg: str):
    """接收日志并存入状态"""
    with _status_lock:
        _status["logs"].append({"time": time.strftime("%H:%M:%S"), "msg": msg})
        # 只保留最近 100 条
        if len(_status["logs"]) > 100:
            _status["logs"] = _status["logs"][-100:]


class WebLiveMonitor(LiveMonitor):
    """带 Web 回调的 LiveMonitor"""

    def _on_audio_chunk(self, audio_path: str):
        """处理新的音频分片"""
        text = self.transcriber.transcribe(audio_path)
        if text:
            with self._buffer_lock:
                self._transcript_buffer.append(text)
                self._all_transcripts.append(text)
            with _status_lock:
                _status["transcript_count"] = len(self._all_transcripts)
            _log_callback(f"识别: {text[:80]}...")

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
                elapsed = int(time.time() - self._start_time)
                minutes = elapsed // 60
                title = f"直播阶段性总结 (第{self._summary_count}次·{minutes}分钟)"
                self.notifier.send_summary(title, summary, is_final=False)
                _log_callback(f"总结已推送: {title}")
                with _status_lock:
                    _status["summary_count"] = self._summary_count


def start_monitor(config_path: str):
    """启动监控"""
    global _monitor, _monitor_thread, _status

    if _status["running"]:
        return False, "监控已在运行中"

    _monitor = WebLiveMonitor(config_path=config_path)

    with _status_lock:
        _status["running"] = True
        _status["start_time"] = time.time()
        _status["summary_count"] = 0
        _status["transcript_count"] = 0
        _status["logs"] = []

    _log_callback("监控启动中...")

    def run():
        try:
            _monitor.start()
        except Exception as e:
            _log_callback(f"监控异常: {e}")
        finally:
            with _status_lock:
                _status["running"] = False

    # start() 会阻塞，需要在单独线程中运行
    # 但 start() 内部已经有自己的循环，我们需要修改调用方式
    _monitor._running = True
    _monitor._start_time = time.time()

    from ..config import setup_logging
    setup_logging(_monitor.config)

    _monitor.notifier.send_text("[启动] 直播监控已启动，正在监听直播内容...")
    _monitor.capture.start()

    summary_thread = threading.Thread(target=_monitor._summary_loop, daemon=True)
    summary_thread.start()

    with _status_lock:
        _status["running"] = True
    _log_callback("监控已启动")

    return True, "启动成功"


def stop_monitor():
    """停止监控"""
    global _monitor, _status

    if not _status["running"] or not _monitor:
        return False, "监控未在运行"

    _log_callback("正在停止监控...")
    _monitor.stop()

    with _status_lock:
        _status["running"] = False

    return True, "已停止"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/start", methods=["POST"])
def api_start():
    config_path = request.json.get("config", "config.yaml") if request.json else "config.yaml"
    ok, msg = start_monitor(config_path)
    return jsonify({"ok": ok, "msg": msg})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    ok, msg = stop_monitor()
    return jsonify({"ok": ok, "msg": msg})


@app.route("/api/summary", methods=["POST"])
def api_summary():
    """手动触发总结（不结束监控）"""
    if not _status["running"] or not _monitor:
        return jsonify({"ok": False, "msg": "监控未在运行"})

    with _monitor._buffer_lock:
        if not _monitor._transcript_buffer and not _monitor._all_transcripts:
            return jsonify({"ok": False, "msg": "暂无识别内容，无法总结"})
        texts = _monitor._transcript_buffer.copy()
        _monitor._transcript_buffer.clear()

    if not texts:
        texts = _monitor._all_transcripts[-20:]  # 取最近20条

    combined_text = "\n".join(texts)
    _monitor._summary_count += 1

    summary = _monitor.summarizer.summarize_interval(combined_text)
    if summary:
        now = time.strftime("%H:%M")
        title = f"直播阶段性总结 (第{_monitor._summary_count}次·{now}·手动)"
        _monitor.notifier.send_summary(title, summary, is_final=False)
        _log_callback(f"手动总结已推送: {title}")
        with _status_lock:
            _status["summary_count"] = _monitor._summary_count
        return jsonify({"ok": True, "msg": "总结已发送"})
    else:
        return jsonify({"ok": False, "msg": "总结生成失败"})


@app.route("/api/status")
def api_status():
    with _status_lock:
        data = dict(_status)
        if data["running"] and data["start_time"]:
            data["elapsed"] = int(time.time() - data["start_time"])
        else:
            data["elapsed"] = 0
    if _monitor:
        data["interval"] = _monitor.summary_interval
        # 计算距离下次总结的剩余秒数
        if data["running"] and data["elapsed"] > 0:
            data["next_summary"] = _monitor.summary_interval - (data["elapsed"] % _monitor.summary_interval)
        else:
            data["next_summary"] = _monitor.summary_interval
    return jsonify(data)


def run_web(host: str = "0.0.0.0", port: int = 5000, config_path: str = "config.yaml"):
    """启动 Web 服务"""
    app.config["CONFIG_PATH"] = config_path
    logger.info(f"Web 控制面板启动: http://localhost:{port}")
    app.run(host=host, port=port, debug=False, threaded=True)
