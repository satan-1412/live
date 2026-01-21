#!/bin/bash
# 不管在哪里运行，先跳到工作目录
cd /sdcard/live || exit
# 创建信号文件
touch run_now_signal
echo "✅ 已发送触发信号！主程序将在 1 秒内响应。"
