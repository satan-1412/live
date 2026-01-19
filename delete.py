import os
import shutil

# =================配置区域=================
# 需要处理的目标文件列表
TARGET_FILES = [
    'TV.m3u8', 
    'no sex/TV_1(no sex).m3u8'
]
# =========================================

def clean_m3u8(filepath):
    if not os.path.exists(filepath):
        print(f"⚠️ 文件未找到: {filepath}")
        return

    print(f"正在处理: {filepath} ...")

    # 1. 制作备份 (Backup)
    # 为了防止误删，在读取前先复制一份 .bak 文件
    backup_path = filepath + ".bak"
    try:
        shutil.copy(filepath, backup_path)
        print(f"   ↳ 已创建备份: {backup_path}")
    except Exception as e:
        print(f"   ❌ 备份失败，停止处理: {e}")
        return

    # 2. 读取内容
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"   ❌ 读取失败: {e}")
        return

    new_lines = []
    
    # 状态机标志：
    # 0 = 普通模式 (寻找 #EXTINF 或处理头部信息)
    # 1 = 刚发现 #EXTINF (下一行必须保留，作为主链接)
    # 2 = 刚保留完主链接 (开启删除模式，直到遇到空行或新频道)
    state = 0
    
    deleted_count = 0

    for line in lines:
        stripped = line.strip()

        # --- 规则1: 遇到空行 -> 必须保留，且重置状态 ---
        if not stripped:
            new_lines.append(line)
            state = 0 # 重置为普通模式，停止删除
            continue

        # --- 规则2: 遇到分类标题 (###) -> 必须保留，且重置状态 ---
        if "###" in stripped:
            new_lines.append(line)
            state = 0
            continue

        # --- 规则3: 遇到新频道头 (#EXTINF) -> 必须保留，且进入链接等待状态 ---
        if stripped.startswith("#EXTINF"):
            new_lines.append(line)
            state = 1 # 下一行是主链接，要留着
            continue

        # --- 内容处理逻辑 ---
        if state == 1:
            # 刚读取完 #EXTINF，这一行是该频道的“主直播链接”
            # 必须保留
            new_lines.append(line)
            state = 2 # 主链接已保存，接下来的非空行都是多余的，准备删除
        
        elif state == 2:
            # 进入了“删除多余源”模式
            # 因为上面没有触发“空行”、“###”、“#EXTINF”的判断
            # 所以这一行就是多余的链接或垃圾数据
            # 动作：跳过不写入 (即删除)
            deleted_count += 1
            # print(f"   [删除] {stripped}") # 调试用，如果想看删了啥可以取消注释
            pass 
        
        else:
            # state == 0 (普通模式)
            # 包含文件头 #EXTM3U 或 #EXT-X-SESSION 等全局配置
            # 保留
            new_lines.append(line)

    # 3. 写入文件
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print(f"   ✅ 清理完成。共删除了 {deleted_count} 行多余内容。")
    except Exception as e:
        print(f"   ❌ 写入失败: {e}")
        # 如果写入失败，尝试从备份恢复
        shutil.copy(backup_path, filepath)
        print("   ↳ 已从备份恢复原文件。")

if __name__ == '__main__':
    for target in TARGET_FILES:
        clean_m3u8(target)
