import json
import subprocess
import os
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================
# ⚙️ 系统核心配置
# ==========================================
TARGET_FILES = ['TV.m3u8', 'no sex/TV_1(no sex).m3u8']
JSON_FILE = 'streams.json'

# [核心修改] 针对 YouTube 直播，使用 iPhone UA 是最稳的，能强制获取 m3u8
UA_IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1'
UA_PC = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

BATCH_SIZE = 10
COOKIE_TEMP_FILE = 'cookies_netscape.txt'

# ==========================================
# 🔐 鉴权模块
# ==========================================
def process_smart_cookies():
    content = None
    if 'YOUTUBE_COOKIES' in os.environ and os.environ['YOUTUBE_COOKIES'].strip():
        print("    [鉴权中心] ☁️ 检测到云端环境变量密钥...")
        content = os.environ['YOUTUBE_COOKIES']
    elif os.path.exists('cookies.txt'):
        try:
            with open('cookies.txt', 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read().strip()
            if content:
                print("    [鉴权中心] 📂 检测到本地凭证文件...")
        except: pass

    if not content: return False

    try:
        # 简单清洗并转换为 Netscape 格式
        if content.startswith('[') or content.startswith('{'):
            try:
                data = json.loads(content)
                if isinstance(data, dict): data = [data]
                with open(COOKIE_TEMP_FILE, 'w', encoding='utf-8') as out:
                    out.write("# Netscape HTTP Cookie File\n")
                    for c in data:
                        if 'domain' not in c or 'name' not in c: continue
                        domain = c.get('domain', '')
                        if not domain.startswith('.'): domain = '.' + domain
                        expiry = str(int(c.get('expirationDate', time.time() + 31536000)))
                        out.write(f"{domain}\tTRUE\t{c.get('path','/')}\tTRUE\t{expiry}\t{c.get('name')}\t{c.get('value')}\n")
                return True
            except: pass

        if "# Netscape" in content or content.count('\t') > 3:
            with open(COOKIE_TEMP_FILE, 'w', encoding='utf-8') as out:
                out.write(content)
            return True
            
        return False
    except: return False

# ==========================================
# 🕷️ 核心解析模块 (V44.0 直播专用优化)
# ==========================================
def get_real_url(url, channel_name, retry_mode=False):
    is_yt = 'youtube.com' in url or 'youtu.be' in url
    
    # 基础命令
    cmd = ['yt-dlp', '-g', '--no-playlist', '--no-check-certificate']
    
    # [关键优化]
    # 1. --force-ipv4: 防止 IPv6 网络波动导致直播断连
    # 2. --no-cache-dir: 防止读取过期的缓存链接
    cmd.extend(['--force-ipv4', '--no-cache-dir'])

    if is_yt:
        # [针对 YouTube] 
        # 使用 iPhone UA -> 骗取 HLS (m3u8) 流
        # protocol^=m3u8 -> 只要 HLS 协议，不要 DASH
        cmd.extend(['--user-agent', UA_IPHONE])
        cmd.extend(['-f', 'best[protocol^=m3u8]/best'])
        cmd.extend(['--referer', 'https://www.youtube.com/'])
    else:
        # [针对其他平台] 使用 PC UA
        cmd.extend(['--user-agent', UA_PC])
        cmd.extend(['-f', 'best[ext=mp4]/best']) 
    
    if is_yt and os.path.exists(COOKIE_TEMP_FILE): 
        cmd.extend(['--cookies', COOKIE_TEMP_FILE])     
    
    cmd.append(url)
    
    try:
        # 增加超时时间，直播流解析有时候比较慢
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if res.returncode == 0:
            raw_output = res.stdout.strip()
            real_url = raw_output.split('\n')[0] if raw_output else None
            
            if real_url and 'http' in real_url:
                return channel_name, real_url, True
    except Exception as e:
        pass
    
    return channel_name, None, False

# ==========================================
# 🚀 主程序
# ==========================================
def update_streams():
    if not os.path.exists(JSON_FILE): return

    process_smart_cookies()
    
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f: data = json.load(f)
    except: return

    # 清理非直播任务
    if "Run_Series_Loop" in data: data.pop("Run_Series_Loop") 
    
    stream_map = {}
    def extract(d):
        for k, v in d.items():
            if isinstance(v, dict): extract(v)
            elif isinstance(v, str) and v.startswith(('http', 'rtmp')): stream_map[k] = v
    extract(data)

    unique_tasks = {}
    # 读取旧文件保持顺序
    for m in TARGET_FILES:
        if os.path.exists(m):
            with open(m, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('#EXTINF:'):
                        name = line.split(',')[-1].strip()
                        if name in stream_map: unique_tasks[name] = stream_map[name]

    live_tasks = [(k, v) for k, v in unique_tasks.items()]
    failed_channels = []
    
    print(f">>> [任务就绪] 直播队列: {len(live_tasks)}")

    # 并发更新
    if live_tasks:
        print(f"\n🚀 [开始抓取] 正在更新直链...")
        with ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
            futures = {executor.submit(get_real_url, u, n, False): n for n, u in live_tasks}
            for future in as_completed(futures):
                n, u, success = future.result()
                if success and u:
                    print(f"   ✅ {n}")
                    unique_tasks[n] = u
                else:
                    print(f"   🌪️ {n} (失败)")
                    # 失败则保留原链接或重试，这里简单记录
                    pass

    # 写入文件
    print("\n💾 [写入文件]")
    for m in TARGET_FILES:
        if not os.path.exists(m): continue
        with open(m, 'r', encoding='utf-8') as f: lines = f.readlines()
        new_lines, idx = [], 0
        while idx < len(lines):
            line = lines[idx]
            if line.startswith('#EXTINF:'):
                name = line.split(',')[-1].strip()
                if name in unique_tasks:
                    new_lines.append(line)
                    new_lines.append(unique_tasks[name] + '\n')
                    idx += 2; continue
            new_lines.append(line); idx += 1
        with open(m, 'w', encoding='utf-8') as f: f.writelines(new_lines)
        print(f"   -> {m} 更新完成")
    
    print("\n✅ 所有任务完成。")

if __name__ == '__main__':
    update_streams()
