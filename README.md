# 高清录屏助手

一个 Python 桌面录屏工具，支持：
- 高清屏幕录制（默认全屏、30 FPS）
- 本地保存视频（MP4）和音频（WAV）
- 实时音频声浪显示（判断是否采集到声音）
- 按住 `Alt` 键进行画面放大（跟随鼠标）
- 按住 `Ctrl` 键将鼠标高亮为红色用于引导视线

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 运行

```bash
python screen_recorder.py
```

## 使用说明

1. 选择保存目录。
2. 点击“开始录制”。
3. 录制过程中：
   - 按住 `Alt`：画面放大。
   - 按住 `Ctrl`：鼠标红色高亮。
4. 点击“停止录制”，会在本地生成：
   - `record_时间戳.mp4`
   - `record_时间戳.wav`

> 提示：如需将音频合并到 MP4，可使用 ffmpeg 后处理。
