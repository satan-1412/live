#!/bin/bash

# ==========================================
# ⚙️ 自动同步工具 (全核自检版)
# ==========================================
# 目标：确保 git, yt-dlp, requests, ffmpeg 全部就绪

TRIGGER_FILE="run_now_signal"
ERROR_LOG="error.log"
WORK_DIR="/sdcard/live"

# --- 异常记录 ---
log_error() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] ❌ $1"
    echo "$msg"
    echo "$msg" >> "$ERROR_LOG"
}

# --- 核心环境自检函数 ---
check_and_install() {
    local cmd_name=$1      # 命令名称 (如 git)
    local install_cmd=$2   # 安装命令 (如 pkg install git)
    local type_name=$3     # 类型显示 (如 系统组件)

    if ! command -v "$cmd_name" &> /dev/null; then
        echo "📦 [自检] 发现缺失 $type_name: $cmd_name"
        echo "   ↳ 正在自动安装..."
        $install_cmd
        
        if [ $? -eq 0 ]; then
            echo "   ✅ 安装成功！"
        else
            log_error "$cmd_name 安装失败，请手动检查网络或源！"
            # 核心组件缺失时，暂停运行以防报错刷屏
            exit 1
        fi
    fi
}

# 切换工作目录
cd "$WORK_DIR" || exit

echo "🔍 [系统] 正在进行全核心自检..."

# 1. 检测 git (同步核心)
check_and_install "git" "pkg install git -y" "系统核心"

# 2. 检测 ffmpeg (流媒体处理核心 - 建议安装)
check_and_install "ffmpeg" "pkg install ffmpeg -y" "流媒体核心"

# 3. 检测 yt-dlp (抓取核心 - pip安装)
if ! command -v yt-dlp &> /dev/null; then
    echo "📦 [自检] 缺失抓取核心: yt-dlp"
    pip install yt-dlp
fi

# 4. 检测 requests (Python依赖)
if ! python -c "import requests" 2>/dev/null; then
    echo "📦 [自检] 缺失 Python 库: requests"
    pip install requests
fi

echo "✅ [系统] 环境完整，引擎启动！"

# --- 主循环 ---
while true
do
    echo "========================================"
    echo "⏰ [时间] $(date '+%H:%M:%S')"
    echo "🚀 [任务] 开始检测并更新链接..."
    
    # 运行 Python 脚本
    python update.py
    
    if [ $? -ne 0 ]; then
        log_error "更新脚本执行异常"
    else
        # Git 同步
        echo "☁️ [Git] 正在同步..."
        cd "$WORK_DIR" # 再次确认目录
        git add .
        git commit --allow-empty -m "Auto Update: $(date +'%H:%M')"
        
        if ! git push; then
            log_error "Git 推送失败"
        else
            echo "✅ [完成] 仓库已同步"
        fi
    fi
    
    echo "⏳ [待机] 进入 1 小时循环..."
    echo "========================================"
    
    # 倒计时逻辑
    count=0
    target=3600
    while [ $count -lt $target ]
    do
        if [ -f "$TRIGGER_FILE" ]; then
            echo "⚡ 收到插队信号！立即执行..."
            rm -f "$TRIGGER_FILE"
            break
        fi
        sleep 1
        count=$((count+1))
    done
done
