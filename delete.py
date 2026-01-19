import os
import shutil

# =================配置区域=================
# 需要处理的目标文件列表
TARGET_FILES = ['TV.m3u8', 'no sex/TV_1(no sex).m3u8']
# =========================================

def process_file(file_path):
    if not os.path.exists(file_path):
        print(f"⚠️ 文件未找到: {file_path}")
        return

    print(f"正在扫描文件: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    original_lines = lines[:] # 复制一份用于对比
    modified = False # 标记是否发生修改
    backup_created = False # 标记本轮是否已创建备份

    # 从上往下扫描，获取所有 #EXTINF 的行号索引
    # 使用列表推导式先锁定所有频道头的位置
    extinf_indices = [i for i, line in enumerate(lines) if line.startswith('#EXTINF:')]

    # 为了防止修改行内容后影响后续索引判断（虽然只是清空内容不删行，索引不变），
    # 但逻辑上我们分别处理“上一行”和“下一行”
    
    lines_to_clear = set() # 记录需要清空的行号

    for idx in extinf_indices:
        # 1. 检查上一行 (idx - 1)
        if idx > 0: # 排除第一行就是 EXTINF 的情况（虽然少见）
            prev_line_idx = idx - 1
            # 如果上一行既不是空行，也不是 M3U 头(#EXTM3U)，则标记清理
            content = lines[prev_line_idx].strip()
            if content and not content.startswith('#EXTM3U'):
                print(f"   [发现多余内容] 频道上方 (行 {prev_line_idx+1}): {content[:30]}...")
                lines_to_clear.add(prev_line_idx)

        # 2. 检查下一行 (链接的下一行 -> idx + 2)
        # 假设 idx 是 EXTINF, idx+1 是 URL, 我们要检查 idx+2
        check_idx = idx + 2
        if check_idx < len(lines):
            content = lines[check_idx].strip()
            # 如果不是空行，且不是下一个频道的开头（防止误删紧凑排列的频道），则标记清理
            # 但根据您的要求：“如果不是空行...上下一行清空”。
            # 如果是紧凑排列的下一个频道，也会被视为“非空行”而被强行清空。
            # 这正是为了去除“多余的频道”或“多余的链接”。
            # 如果文件本身是紧凑排列的（频道连着频道），这步操作会删除下一个频道！
            # 鉴于您提到“直播源后面多余的频道”，通常是指 yt-dlp 生成的第二个音频链接。
            # 我们严格执行您的指令：只要不是空行，就清空。备份文件会保护数据。
            if content:
                print(f"   [发现多余内容] 频道下方 (行 {check_idx+1}): {content[:30]}...")
                lines_to_clear.add(check_idx)

    # 执行修改
    if lines_to_clear:
        # 只要有需要修改的地方，且还没备份过，就先备份
        if not backup_created:
            backup_path = file_path + ".bak"
            shutil.copy2(file_path, backup_path)
            print(f"   🛡️ 已创建备份: {backup_path}")
            backup_created = True

        for i in lines_to_clear:
            lines[i] = "\n" # 替换为空行
        
        modified = True

    # 写入文件
    if modified:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print(f"✅ 文件清理完成: {file_path}\n")
    else:
        print(f"✨ 文件无需清理: {file_path}\n")

if __name__ == '__main__':
    for target in TARGET_FILES:
        process_file(target)
