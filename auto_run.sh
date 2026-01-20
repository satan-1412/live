#!/bin/bash

# ==========================================
# ⚙️ 自动同步工具 (独立运行版)
# ==========================================
# 仅负责更新链接与上传仓库，不涉及服务器管理

TRIGGER_FILE="run_now_signal"
ERROR_LOG="error.log"

# --- 异常记录 ---
log_error() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] ❌ $1"
    echo "$msg"
    echo "$msg" >> "$ERROR_LOG"
}

while true
do
    echo "========================================"
    echo "⏰ [时间] $(date '+%H:%M:%S')"
    echo "🚀 [任务] 开始检测并更新链接..."
    
    # 运行核心更新脚本
    python update.py
    
    if [ $? -ne 0 ]; then
        log_error "更新脚本执行失败，请检查配置！"
    else
        # Git 同步流程
        echo "☁️ [Git] 正在同步..."
        git add .
        
        # ⚠️ 修改点：强制提交，允许空提交 (--allow-empty)，确保每次都上传
        git commit --allow-empty -m "Auto Update: $(date +'%H:%M')"
        
        if ! git push; then
            log_error "Git 推送失败 (网络或权限)"
        else
            echo "✅ [完成] 仓库已更新 (强制同步)"
        fi
    fi
    
    echo "⏳ [待机] 进入 1 小时循环 (期间运行 run_now.sh 可触发)..."
    echo "========================================"
    
    # 倒计时循环
    count=0
    target=3600
    while [ $count -lt $target ]
    do
        if [ -f "$TRIGGER_FILE" ]; then
            echo "⚡ 收到立即执行信号..."
            rm -f "$TRIGGER_FILE"
            break
        fi
        
        sleep 1
        count=$((count+1))
    done
done
