#!/bin/bash
# 快速触发脚本 - 带基础环境修复

cd /sdcard/live || exit

echo "🔍 正在检查运行环境..."

# 1. 快速修补 requests
if ! python -c "import requests" 2>/dev/null; then
    echo "🔧 补全 requests..."
    pip install requests -q
fi

# 2. 快速修补 yt-dlp
if ! command -v yt-dlp &> /dev/null; then
    echo "🔧 补全 yt-dlp..."
    pip install yt-dlp -q
fi

# 发送信号
touch run_now_signal
echo "✅ 信号已发送！主程序将立即响应。"
