# 抖音直播监控智能体

自动监控抖音直播间内容，通过 AI 实时总结并推送到飞书群。

## 功能特性

- **Web 控制面板** — 浏览器点击开始/结束，实时查看状态和日志
- **麦克风录音** — 手机打开直播间外放，电脑麦克风即可录制
- **语音识别** — 小米大模型 mimo-v2.5-asr 中文语音转文字
- **AI 智能总结** — 小米大模型 mimo-v2.5 生成阶段性摘要和完整总结
- **飞书推送** — 通过 Webhook 机器人发送格式化消息卡片

## 架构设计

```
手机外放直播声音 → 电脑麦克风录音 → ffmpeg 音频切片
    ↓
小米 ASR 语音识别 → 文本累积缓冲区
    ↓
定时触发 AI 总结 → 飞书 Webhook 推送
```

## 快速开始

### 1. 安装依赖

```bash
# 安装系统依赖 (macOS)
brew install ffmpeg

# 安装 Python 依赖
pip install -r requirements.txt
```

### 2. 配置

```bash
cp config.yaml.example config.yaml
# 编辑 config.yaml 填入你的配置
```

需要配置的关键项：
- `whisper.api_key` — 小米大模型 API Key
- `whisper.base_url` — 小米 API 地址
- `summarize.api_key` — 小米大模型 API Key
- `summarize.base_url` — 小米 API 地址
- `feishu.webhook_url` — 飞书机器人 Webhook URL

### 3. 获取飞书 Webhook

1. 打开飞书群 → 设置 → 群机器人
2. 添加机器人 → 自定义机器人
3. 复制 Webhook URL 填入配置文件

### 4. 运行

```bash
# Web 控制面板模式 (推荐)
python run.py --web --port 9090
# 浏览器打开 http://localhost:9090

# 命令行模式
python run.py
# 输入 q + 回车 结束并生成总结

# 指定配置文件
python run.py --web -c my_config.yaml
```

## 使用方法

1. 启动程序，打开 Web 控制面板
2. 手机打开抖音直播间，外放声音
3. 点击「开始监控」
4. 每隔 1 小时自动总结推送到飞书
5. 点击「结束监控」生成完整总结报告

## 项目结构

```
douyin-live-monitor/
├── run.py                    # 启动入口
├── config.yaml.example      # 配置模板
├── requirements.txt          # Python 依赖
└── src/
    ├── main.py               # 主控制器 (LiveMonitor)
    ├── config.py             # 配置管理
    ├── capture/
    │   └── stream_capture.py # 音频捕获 (麦克风/系统音频/流抓取)
    ├── transcribe/
    │   └── whisper_transcriber.py  # 语音识别 (OpenAI/小米 ASR)
    ├── summarize/
    │   └── gpt_summarizer.py # AI 总结 (OpenAI/小米)
    ├── notify/
    │   └── feishu.py         # 飞书消息推送
    └── web/
        ├── app.py            # Web 控制面板后端
        └── templates/
            └── index.html    # 控制面板页面
```

## 配置说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `stream.mode` | 捕获模式: mic/system_audio/stream/auto | mic |
| `stream.audio_device` | 音频设备索引 | 0 (MacBook 麦克风) |
| `stream.chunk_duration` | 音频分片时长(秒) | 30 |
| `whisper.base_url` | ASR API 地址 | 小米 API |
| `whisper.model` | ASR 模型 | mimo-v2.5-asr |
| `summarize.base_url` | 总结 API 地址 | 小米 API |
| `summarize.model` | 总结模型 | mimo-v2.5 |
| `summarize.interval` | 总结间隔(秒) | 3600 |
| `feishu.webhook_url` | 飞书 Webhook | 必填 |

## 注意事项

- 需要小米大模型 API 账户和额度
- 建议在安静环境下使用麦克风模式，或使用耳机线连接手机
- 音频分片时长影响识别精度和 API 调用频率，建议 20-60 秒
- Web 控制面板默认端口 9090，可通过 `--port` 修改

## 扩展方向

- 添加弹幕/评论监控 (浏览器自动化)
- 支持多直播间同时监控
- 接入本地 Whisper 模型减少 API 成本
- 添加关键词告警触发
- WebSocket 实时日志推送
