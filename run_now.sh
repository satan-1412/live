#!/bin/bash
cd /sdcard/live
# 创建信号文件
touch run_now_signal
echo "✅ 已发送触发信号！主程序将在 1 秒内响应。"
# 可选：如果你想确认 server 状态
if pgrep -f "python server.py" > /dev/null; then
    echo "🟢 直播后端正在运行中。"
else
    echo "🔴 警告：直播后端未运行！auto_run.sh 下次循环会自动启动它。"
fi
