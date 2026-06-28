# 抖音直播监控智能体

自动监控抖音直播间内容，通过 AI 实时总结并推送到飞书群。

## 功能特性

- **实时音频捕获** - 通过 streamlink 获取直播流，ffmpeg 切分为音频片段
- **语音识别** - 使用 OpenAI Whisper API 进行中文语音转文字
- **AI 智能总结** - GPT 模型生成阶段性摘要和完整总结报告
- **飞书推送** - 通过 Webhook 机器人发送格式化消息卡片

## 架构设计

```
抖音直播流 → streamlink 抓流 → ffmpeg 音频切片
    ↓
Whisper API 语音识别 → 文本累积缓冲区
    ↓
定时触发 GPT 总结 → 飞书 Webhook 推送
```

## 快速开始

### 1. 安装依赖

```bash
# 安装系统依赖 (macOS)
brew install ffmpeg streamlink

# 安装 Python 依赖
pip install -r requirements.txt
```

### 2. 配置

```bash
cp config.yaml.example config.yaml
# 编辑 config.yaml 填入你的配置
```

需要配置的关键项：
- `stream.live_url` - 抖音直播间地址
- `whisper.api_key` - OpenAI API Key (用于语音识别)
- `summarize.api_key` - OpenAI API Key (用于 AI 总结)
- `feishu.webhook_url` - 飞书机器人 Webhook URL

### 3. 获取飞书 Webhook

1. 打开飞书群 → 设置 → 群机器人
2. 添加机器人 → 自定义机器人
3. 复制 Webhook URL 填入配置文件

### 4. 运行

```bash
python run.py
# 或指定配置文件
python run.py -c my_config.yaml
```

按 `Ctrl+C` 停止，会自动生成最终总结报告。

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
    │   └── stream_capture.py # 直播流音频捕获
    ├── transcribe/
    │   └── whisper_transcriber.py  # Whisper 语音识别
    ├── summarize/
    │   └── gpt_summarizer.py # GPT 内容总结
    └── notify/
        └── feishu.py         # 飞书消息推送
```

## 配置说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `stream.live_url` | 抖音直播间 URL | 必填 |
| `stream.chunk_duration` | 音频分片时长(秒) | 30 |
| `whisper.language` | 识别语言 | zh |
| `summarize.interval` | 阶段性总结间隔(秒) | 600 |
| `summarize.final_summary` | 是否生成最终总结 | true |

## 注意事项

- 需要 OpenAI API 账户和额度
- streamlink 对抖音的支持可能随时变化，如遇问题可考虑浏览器自动化方案
- 建议在稳定的网络环境下运行
- 音频分片时长影响识别精度和 API 调用频率，建议 20-60 秒

## 扩展方向

- 添加弹幕/评论监控 (浏览器自动化)
- 支持多直播间同时监控
- 接入本地 Whisper 模型减少 API 成本
- 添加关键词告警触发
