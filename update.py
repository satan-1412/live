import json
import subprocess
import os
import time
import re
import requests
import urllib3
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================
# ⚙️ 系统核心配置
# ==========================================
TARGET_FILES = ['TV.m3u8', 'no sex/TV_1(no sex).m3u8']
JSON_FILE = 'streams.json'

# 屏蔽 requests 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 🎭 身份伪装库 (User-Agent Pool)
# ==========================================
# 策略：针对国内电视台，优先使用移动端 UA，因为它们通常会直接暴露 HLS 链接
UA_POOL = {
    "Android": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "iOS": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "PC": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

BATCH_SIZE = 10     
COOKIE_TEMP_FILE = 'cookies_netscape.txt'

# ==========================================
# 🔐 鉴权凭证处理
# ==========================================
def process_smart_cookies():
    content = None
    if 'YOUTUBE_COOKIES' in os.environ and os.environ['YOUTUBE_COOKIES'].strip():
        print("    [鉴权中心] ☁️ 检测到云端环境变量密钥，正在加载...")
        content = os.environ['YOUTUBE_COOKIES']
    elif os.path.exists('cookies.txt'):
        try:
            with open('cookies.txt', 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read().strip()
            if content:
                print("    [鉴权中心] 📂 检测到本地凭证文件，正在加载...")
        except: pass

    if not content: return False

    try:
        # 兼容 JSON 和 Netscape 格式
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
        
        # 简单兼容模式
        with open(COOKIE_TEMP_FILE, 'w', encoding='utf-8') as out:
            out.write("# Netscape HTTP Cookie File\n")
            expiry = str(int(time.time() + 31536000))
            for pair in content.split(';'):
                if '=' in pair:
                    try:
                        name, value = pair.strip().split('=', 1)
                        out.write(f".youtube.com\tTRUE\t/\tTRUE\t{expiry}\t{name}\t{value}\n")
                    except: continue
        return True
    except Exception:
        return False

# --- 🕸️ 暴力网页嗅探器 (Hunter Mode) ---
def clean_url(url):
    """清理并验证 URL"""
    try:
        # 1. 解码 URL 编码 (http%3A%2F%2F -> http://)
        url = urllib.parse.unquote(url)
        # 2. 处理 JSON Unicode 转义 (\u002F -> /)
        url = url.encode('utf-8').decode('unicode_escape')
        # 3. 处理反斜杠转义 (\/ -> /)
        url = url.replace('\\/', '/')
        return url.strip()
    except:
        return url

def find_m3u8_deep(text):
    """
    [核心算法] 在任意文本中暴力搜索 .m3u8
    """
    candidates = []
    # 策略1：寻找标准 http...m3u8 (忽略空白字符)
    pattern1 = r'(http[s]?://[^\s"\'<>{}|\\^`]+?\.m3u8[^\s"\'<>{}|\\^`]*)'
    matches = re.findall(pattern1, text, re.I)
    candidates.extend(matches)

    # 策略2：寻找被转义的链接 (http:\/\/...)
    pattern2 = r'(http[s]?:\\?/\\?/[^\s"\'<>]+?\.m3u8[^\s"\'<>]*)'
    matches2 = re.findall(pattern2, text, re.I)
    candidates.extend(matches2)

    # 清洗并去重
    for u in candidates:
        clean = clean_url(u)
        # 过滤非 m3u8 或过短的无效链接
        if 'http' in clean and '.m3u8' in clean and len(clean) > 10:
            return clean # 找到第一个看似有效的就返回
    
    return None

def sniff_single_ua(url, ua, depth=0):
    """单次嗅探逻辑"""
    if depth > 1: return None 

    try:
        headers = {
            'User-Agent': ua,
            'Referer': url, # 关键：很多网站检查来源
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }
        
        # 增加 verify=False 忽略证书错误
        response = requests.get(url, headers=headers, timeout=10, verify=False, allow_redirects=True)
        response.encoding = response.apparent_encoding 
        html = response.text
        
        # 1. 🔍 第一轮：直接暴力搜索当前页面的 m3u8
        found_url = find_m3u8_deep(html)
        if found_url: return found_url

        # 2. 📡 第二轮：扫描内嵌窗口 (Iframe) -> 穿透
        iframe_pattern = r'<iframe[^>]+src=["\']([^"\']+)["\']'
        iframes = re.findall(iframe_pattern, html, re.I)
        
        for iframe_src in iframes:
            full_iframe_url = urllib.parse.urljoin(url, iframe_src)
            if 'ad' in full_iframe_url or 'google' in full_iframe_url: continue

            # 递归：钻进去找
            deep_found = sniff_single_ua(full_iframe_url, ua, depth + 1)
            if deep_found: return deep_found

    except Exception:
        pass
    return None

# --- 核心解析模块 (混合引擎版) ---
def get_real_url(url, channel_name, retry_mode=False):
    is_yt = 'youtube.com' in url or 'youtu.be' in url
    
    # -------------------------------
    # 策略 A: 油管专用 (yt-dlp)
    # -------------------------------
    if is_yt:
        cmd = ['yt-dlp', '-g', '--no-playlist', '--no-check-certificate', '--user-agent', UA_POOL["PC"]]
        cmd.extend(['-f', 'best[protocol^=m3u8]/best'])
        cmd.extend(['--referer', 'https://www.youtube.com/'])
        if os.path.exists(COOKIE_TEMP_FILE): cmd.extend(['--cookies', COOKIE_TEMP_FILE])
        cmd.append(url)
        
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
            if res.returncode == 0:
                raw = res.stdout.strip().split('\n')[0]
                if raw and 'http' in raw: return channel_name, raw, True
        except: pass
    
    # -------------------------------
    # 策略 B: 网站轮询嗅探 (多 UA 轮战)
    # -------------------------------
    else:
        # 定义轮询顺序：安卓 -> iOS -> 电脑
        # 手机端通常更容易获得无加密的 HLS 流
        ua_order = ["Android", "iOS", "PC"]
        
        for ua_type in ua_order:
            current_ua = UA_POOL[ua_type]
            
            # 1. 尝试 Python 暴力嗅探
            sniffed_url = sniff_single_ua(url, current_ua)
            if sniffed_url:
                # 找到后直接返回，不再尝试其他 UA
                return channel_name, sniffed_url, True
            
            # 2. 如果嗅探失败，尝试用当前 UA 跑一次 yt-dlp (捡漏)
            cmd = ['yt-dlp', '-g', '--no-playlist', '--no-check-certificate', '--user-agent', current_ua]
            cmd.append(url)
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                if res.returncode == 0:
                    raw = res.stdout.strip().split('\n')[0]
                    if raw and 'http' in raw: return channel_name, raw, True
            except: pass
            
            # 如果当前 UA 失败，循环继续，尝试下一个 UA...

    return channel_name, None, False

# --- 主程序入口 ---
def update_streams():
    if not os.path.exists(JSON_FILE): return

    # 1. 执行鉴权
    process_smart_cookies()
    
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
    
    print(f">>> [任务就绪] 直播队列: {len(live_tasks)}")

    # Phase 1: 批量并发
    if live_tasks:
        print(f"\n========================================")
        print(f"🚀 [第一阶段] 正在更新直播频道...")
        print(f"========================================")
        
        for i in range(0, len(live_tasks), BATCH_SIZE):
            batch = live_tasks[i:i+BATCH_SIZE]
            print(f"\n⚡ [批次执行] 序列: {i//BATCH_SIZE + 1}...")
            
            with ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
                futures = {executor.submit(get_real_url, u, n, False): n for n, u in batch}
                for future in as_completed(futures):
                    n, u, success = future.result()
                    if success and u:
                        # 标记来源
                        is_sniffed = '.m3u8' in u and 'googlevideo' not in u and 'bilivideo' not in u
                        tag = "🔍 [嗅探成功]" if is_sniffed else "✅ [解析成功]"
                        print(f"   {tag} {n}") 
                        unique_tasks[n] = u
                    else:
                        print(f"   🌪️ [暂缓处理] {n}")
                        orig = next((url for name, url in batch if name == n), None)
                        if orig: failed_channels.append((n, orig))
            time.sleep(0.5)

    # Phase 2: 重试 (最终挽救)
    if failed_channels:
        print(f"\n========================================")
        print(f"🔄 [最终挽救] 集中处理所有异常任务...")
        print(f"========================================")
        
        print(f"   >>> 正在修复 {len(failed_channels)} 个直播信号...")
        for idx, (n, u) in enumerate(failed_channels):
            print(f"   🛠️ [正在修复] {n} ...")
            retry_success = False
            # 重试时，get_real_url 会再次跑一遍完整的 UA 轮询逻辑
            for r_attempt in range(1, 2): 
                _, new_u, success = get_real_url(u, n, True)
                if success and new_u:
                    print(f"      ✅ [回滚成功] 链路已恢复")
                    unique_tasks[n] = new_u
                    retry_success = True
                    break
                else:
                    time.sleep(1)
            if not retry_success: print(f"      ❌ [最终熔断] 无法接通，已弃用")

    # I/O 写入
    print("\n>>> [I/O 操作] 正在写入目标文件...")
    for m in TARGET_FILES:
        if not os.path.exists(m): continue
        
        with open(m, 'r', encoding='utf-8') as f: lines = f.readlines()
        new_lines, idx, cnt = [], 0, 0
        while idx < len(lines):
            line = lines[idx]
            if line.startswith('#EXTINF:'):
                name = line.split(',')[-1].strip()
                if name in unique_tasks:
                    new_lines.append(line)
                    new_lines.append(unique_tasks[name] + '\n')
                    idx += 2; cnt += 1; continue
            new_lines.append(line); idx += 1
        with open(m, 'w', encoding='utf-8') as f: f.writelines(new_lines)
        print(f"   -> {m}: 更新记录 {cnt} 条")
    
    print("\n✅ [执行完毕] 所有计划任务已完成。")

if __name__ == '__main__':
    update_streams()
