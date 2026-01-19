import json
import subprocess
import os
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================
# ⚙️ 系统核心配置 (System Configuration)
# ==========================================
TARGET_FILES = ['TV.m3u8', 'no sex/TV_1(no sex).m3u8']
JSON_FILE = 'streams.json'

# [关键] 必须让播放器也使用这个 UA，否则 YouTube 会报 403
UA_IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1'

BATCH_SIZE = 10     
COOKIE_TEMP_FILE = 'cookies_netscape.txt' 

# ==========================================
# 🔐 鉴权凭证处理
# ==========================================
def process_smart_cookies():
    content = None
    if 'YOUTUBE_COOKIES' in os.environ and os.environ['YOUTUBE_COOKIES'].strip():
        content = os.environ['YOUTUBE_COOKIES']
    elif os.path.exists('cookies.txt'):
        try:
            with open('cookies.txt', 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read().strip()
        except: pass
    if not content: return False
    try:
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

# --- 核心解析模块 (针对直播/首播优化) ---
def get_real_url(url, channel_name):
    is_yt = 'youtube.com' in url or 'youtu.be' in url
    # 清理移动端链接前缀
    url = url.replace('m.youtube.com', 'www.youtube.com')
    
    cmd = ['yt-dlp', '-g', '--no-playlist', '--no-check-certificate', '--force-ipv4', '--no-cache-dir']
    
    if is_yt:
        cmd.extend(['--user-agent', UA_IPHONE])
        # 强制只拿 m3u8 (HLS) 协议，这对电台直播至关重要
        cmd.extend(['-f', 'best[protocol^=m3u8]/best'])
        cmd.extend(['--referer', 'https://www.youtube.com/'])
        if os.path.exists(COOKIE_TEMP_FILE): cmd.extend(['--cookies', COOKIE_TEMP_FILE])     
    else:
        cmd.extend(['-f', 'best[ext=mp4]/best']) 
    
    cmd.append(url)
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if res.returncode == 0:
            real_url = res.stdout.strip().split('\n')[0]
            if real_url and 'http' in real_url:
                return channel_name, real_url, True
    except: pass
    return channel_name, None, False

# --- 主程序入口 ---
def update_streams():
    if not os.path.exists(JSON_FILE): return
    process_smart_cookies()
    with open(JSON_FILE, 'r', encoding='utf-8') as f: data = json.load(f)
    if "Run_Series_Loop" in data: data.pop("Run_Series_Loop") 
    
    stream_map = {}
    def extract(d):
        for k, v in d.items():
            if isinstance(v, dict): extract(v)
            elif isinstance(v, str) and v.startswith(('http', 'rtmp')): stream_map[k] = v
    extract(data)

    unique_tasks = {}
    for m in TARGET_FILES:
        if os.path.exists(m):
            with open(m, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('#EXTINF:'):
                        name = line.split(',')[-1].strip()
                        if name in stream_map: unique_tasks[name] = stream_map[name]

    live_tasks = [(k, v) for k, v in unique_tasks.items()]
    if live_tasks:
        print(f"\n🚀 [开始抓取] 正在更新直链 (V45.0)...")
        with ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
            futures = {executor.submit(get_real_url, u, n): n for n, u in live_tasks}
            for future in as_completed(futures):
                n, u, success = future.result()
                if success and u:
                    print(f"   ✅ {n}")
                    unique_tasks[n] = u
                else:
                    print(f"   ❌ {n} (抓取失败)")

    print("\n>>> [I/O 操作] 正在写入带有伪装指令的列表...")
    for m in TARGET_FILES:
        if not os.path.exists(m): continue
        with open(m, 'r', encoding='utf-8') as f: lines = f.readlines()
        new_lines, idx = [], 0
        while idx < len(lines):
            line = lines[idx]
            if line.startswith('#EXTINF:'):
                name = line.split(',')[-1].strip()
                if name in unique_tasks:
                    url = unique_tasks[name]
                    new_lines.append(line)
                    # [核心改动] 为 YouTube 链接注入播放器端伪装指令
                    if "googlevideo.com" in url or "youtube.com" in url:
                        # 注入 VLC 和部分播放器通用的 User-Agent 指令
                        new_lines.append(f'#EXTVLCOPT:http-user-agent={UA_IPHONE}\n')
                        new_lines.append(f'#EXTVLCOPT:http-referrer=https://www.youtube.com/\n')
                        # 注入部分安卓播放器通用的 HTTP 头部指令
                        ua_json = json.dumps({"User-Agent": UA_IPHONE, "Referer": "https://www.youtube.com/"})
                        new_lines.append(f'#EXTHTTP:{ua_json}\n')
                    new_lines.append(url + '\n')
                    idx += 2; continue
            new_lines.append(line); idx += 1
        with open(m, 'w', encoding='utf-8') as f: f.writelines(new_lines)
    print("\n✅ 所有任务完成，请直接在播放器中测试。")

if __name__ == '__main__':
    update_streams()
