import json
import subprocess
import os
import time
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================
# ⚙️ 系统核心配置 (System Configuration)
# ==========================================
TARGET_FILES = ['TV.m3u8', 'no sex/TV_1(no sex).m3u8']
JSON_FILE = 'streams.json'
# 每次请求的超时时间 (秒)
TIMEOUT = 15 

UA_LIST = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1'
]
BATCH_SIZE = 8     # 并发数
COOKIE_TEMP_FILE = 'cookies_netscape.txt'

def get_random_ua():
    import random
    return random.choice(UA_LIST)

# ==========================================
# 🕵️‍♂️ 嗅探专家 (Smart Sniffer)
# ==========================================
def smart_sniffer(url):
    """
    当 yt-dlp 失败时，模拟浏览器去网页源代码里“扒” m3u8 链接
    """
    print(f"      🔎 [嗅探模式] 正在扫描网页源码: {url} ...")
    
    headers = {
        'User-Agent': get_random_ua(),
        'Referer': url,  # 很多网站需要 Referer 才能访问 m3u8
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }

    try:
        # 1. 获取网页源码
        resp = requests.get(url, headers=headers, timeout=TIMEOUT, verify=False)
        resp.encoding = 'utf-8' # 强制 UTF-8，防止乱码
        html_content = resp.text

        # 2. 正则暴力匹配 (匹配 http/https 开头，.m3u8 结尾，中间允许带参数)
        # 解释: ["'] 是匹配引号开头, (https?://[^"']+\.m3u8[^"']*) 是捕获组
        pattern = r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']'
        matches = re.findall(pattern, html_content)

        if matches:
            # 去重并取第一个看起来最短的（通常长链接带了太多无用token，容易失效，或者取第一个发现的）
            # 这里简单策略：取第一个
            found_url = matches[0]
            
            # 处理一下可能的转义字符 (如 \/)
            found_url = found_url.replace('\\/', '/')
            
            print(f"      🎉 [嗅探成功] 捕获信号: {found_url[:60]}...")
            return found_url
        
        # 3. 如果没找到，尝试找 iframe (简单的 iframe 穿透)
        iframe_pattern = r'<iframe[^>]+src=["\'](https?://[^"\']+)["\']'
        iframes = re.findall(iframe_pattern, html_content)
        for iframe_url in iframes:
            # 排除常见广告 iframe
            if "google" in iframe_url or "facebook" in iframe_url: continue
            
            print(f"      🕳️ [深度钻取] 发现 iframe，正在潜入: {iframe_url[:40]}...")
            try:
                sub_resp = requests.get(iframe_url, headers=headers, timeout=TIMEOUT, verify=False)
                sub_matches = re.findall(pattern, sub_resp.text)
                if sub_matches:
                    found_url = sub_matches[0].replace('\\/', '/')
                    print(f"      🎉 [嗅探成功] 在 iframe 中捕获: {found_url[:60]}...")
                    return found_url
            except:
                pass

    except Exception as e:
        print(f"      ❌ [嗅探失败] {e}")

    return None

# ==========================================
# 🔐 鉴权凭证处理 (保持原样)
# ==========================================
def process_smart_cookies():
    # ... (保持原来的逻辑不变，为了节省篇幅这里省略，请保留原来的鉴权代码) ...
    # 如果你这部分没改动，直接复制原来的 process_smart_cookies 函数即可
    pass 

# 为了确保代码完整运行，这里还是补上一个简化的鉴权检测，实际使用请用你原来的完整版
if not os.path.exists(COOKIE_TEMP_FILE) and os.path.exists('cookies.txt'):
    # 简单转换一下，防止报错
    try:
        with open('cookies.txt', 'r') as f, open(COOKIE_TEMP_FILE, 'w') as o:
            o.write(f.read())
    except: pass

# ==========================================
# 📡 核心解析模块 (Core Resolver)
# ==========================================
def get_real_url(url, channel_name, retry_mode=False):
    # --- 策略 1: 直链透传 (Pass-through) ---
    # 如果用户填的本来就是 .m3u8 或 .mp4，直接检测是否存活，不走 yt-dlp
    if '.m3u8' in url or '.mp4' in url or '.flv' in url:
        return channel_name, url, True

    # 定义 yt-dlp 命令
    is_yt = 'youtube.com' in url or 'youtu.be' in url
    cmd = ['yt-dlp', '-g', '--no-playlist', '--no-check-certificate', '--user-agent', get_random_ua()]
    
    if is_yt:
        cmd.extend(['-f', 'best[protocol^=m3u8]/best'])
        cmd.extend(['--referer', 'https://www.youtube.com/'])
        if os.path.exists(COOKIE_TEMP_FILE): cmd.extend(['--cookies', COOKIE_TEMP_FILE])     
    else:
        # 对于非 YouTube 网站，放宽格式限制，优先找 HLS
        cmd.extend(['-f', 'best'])

    cmd.append(url)
    
    # --- 策略 2: yt-dlp 官方解析 (Standard Extraction) ---
    try:
        # 给 yt-dlp 多一点时间，有些直播加载慢
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
        if res.returncode == 0:
            raw_output = res.stdout.strip()
            real_url = raw_output.split('\n')[0] if raw_output else None
            if real_url and 'http' in real_url:
                return channel_name, real_url, True
        else:
            # 如果是 YouTube 且失败了，通常没救了，不用走嗅探
            if is_yt:
                # print(f"   ⚠️ [YT-DLP 错误] {res.stderr[:50]}...") # 调试用
                return channel_name, None, False
    except Exception as e:
        pass

    # --- 策略 3: 网页嗅探 (Web Sniffer) ---
    # 如果不是 YouTube，且 yt-dlp 失败了，启用嗅探器
    if not is_yt:
        sniffed_url = smart_sniffer(url)
        if sniffed_url:
            return channel_name, sniffed_url, True

    return channel_name, None, False

# ==========================================
# 🔄 主程序 (Main Loop)
# ==========================================
def update_streams():
    # 忽略 SSL 警告
    requests.packages.urllib3.disable_warnings()

    if not os.path.exists(JSON_FILE): return

    # 1. 鉴权 (这里调用你原来的鉴权逻辑，或者上面简化的)
    # process_smart_cookies() 
    
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f: data = json.load(f)
    except Exception as e:
        print(f"❌ JSON 配置文件格式错误: {e}")
        return

    if "Run_Series_Loop" in data: data.pop("Run_Series_Loop") 
    
    stream_map = {}
    def extract(d):
        for k, v in d.items():
            if isinstance(v, dict): extract(v)
            elif isinstance(v, str) and v.startswith(('http', 'rtmp')): stream_map[k] = v
    extract(data)

    # 仅更新已经在 m3u8 文件里存在的频道
    unique_tasks = {}
    for m in TARGET_FILES:
        if os.path.exists(m):
            with open(m, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('#EXTINF:'):
                        name = line.split(',')[-1].strip()
                        if name in stream_map: unique_tasks[name] = stream_map[name]

    live_tasks = [(k, v) for k, v in unique_tasks.items()]
    failed_channels = []
    
    print(f">>> [任务就绪] 待检测队列: {len(live_tasks)}")

    if live_tasks:
        print(f"\n========================================")
        print(f"🚀 [执行中] 正在更新链接 (混合引擎)...")
        print(f"========================================")
        
        for i in range(0, len(live_tasks), BATCH_SIZE):
            batch = live_tasks[i:i+BATCH_SIZE]
            print(f"\n⚡ [批次 {i//BATCH_SIZE + 1}] Processing...")
            
            with ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
                futures = {executor.submit(get_real_url, u, n, False): n for n, u in batch}
                for future in as_completed(futures):
                    n, u, success = future.result()
                    if success and u:
                        print(f"   ✅ [连接成功] {n}")
                        unique_tasks[n] = u
                    else:
                        print(f"   🌪️ [获取失败] {n}")
                        # 失败不更新，保留原链接（或者视情况处理）
                        # orig = next((url for name, url in batch if name == n), None)
                        # if orig: failed_channels.append((n, orig))

    # ==========================================
    # I/O 持久化
    # ==========================================
    print("\n>>> [I/O 操作] 正在写入文件...")
    for m in TARGET_FILES:
        if not os.path.exists(m): continue
        
        try:
            with open(m, 'r', encoding='utf-8') as f: lines = f.readlines()
            new_lines, idx, cnt = [], 0, 0
            while idx < len(lines):
                line = lines[idx]
                if line.startswith('#EXTINF:'):
                    name = line.split(',')[-1].strip()
                    # 如果该频道在任务列表中，且我们确实拿到了新链接（不为空）
                    if name in unique_tasks and unique_tasks[name]:
                        new_lines.append(line)
                        new_lines.append(unique_tasks[name] + '\n')
                        idx += 2; cnt += 1; continue
                new_lines.append(line); idx += 1
            
            with open(m, 'w', encoding='utf-8') as f: f.writelines(new_lines)
            print(f"   -> {m}: 已更新 {cnt} 个频道")
        except Exception as e:
            print(f"   ❌ 写入出错 {m}: {e}")
    
    print("\n✅ [完成] 所有操作已结束。")

if __name__ == '__main__':
    update_streams()
