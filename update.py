import json
import subprocess
import os
import time
import re
import requests
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================
# ⚙️ 系统核心配置 (System Configuration)
# ==========================================
TARGET_FILES = ['TV.m3u8', 'no sex/TV_1(no sex).m3u8']
JSON_FILE = 'streams.json'

# 屏蔽 requests 请求 verify=False 时的烦人警告，保持界面清爽
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

UA_LIST = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1'
]
BATCH_SIZE = 10     # 并发处理阈值
COOKIE_TEMP_FILE = 'cookies_netscape.txt' # 仅作为运行时临时文件，不上传

def get_random_ua():
    import random
    return random.choice(UA_LIST)

# ==========================================
# 🔐 鉴权凭证处理子系统 (Credential Subsystem)
# ==========================================
def process_smart_cookies():
    """
    [鉴权逻辑] 优先从云端环境变量加载，避免本地文件依赖
    """
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

    if not content: 
        print("    [鉴权中心] ⚠️ 未检测到有效凭证，将以访客模式运行。")
        return False

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
                print(f"    [鉴权中心] ✅ JSON 格式凭证转换完毕")
                return True
            except:
                print(f"    [鉴权中心] ⚠️ JSON 解析异常，尝试切换至兼容模式...")

        if "# Netscape" in content or content.count('\t') > 3:
            with open(COOKIE_TEMP_FILE, 'w', encoding='utf-8') as out:
                out.write(content)
            print(f"    [鉴权中心] ✅ 标准 Netscape 格式加载完毕")
            return True

        print("    [鉴权中心] ⚠️ 格式未识别，启用启发式兼容模式...")
        with open(COOKIE_TEMP_FILE, 'w', encoding='utf-8') as out:
            out.write("# Netscape HTTP Cookie File\n")
            expiry = str(int(time.time() + 31536000))
            for pair in content.split(';'):
                if '=' in pair:
                    try:
                        name, value = pair.strip().split('=', 1)
                        out.write(f".youtube.com\tTRUE\t/\tTRUE\t{expiry}\t{name}\t{value}\n")
                    except: continue
        print(f"    [鉴权中心] ✅ 兼容性转换完成")
        return True

    except Exception as e:
        print(f"    [鉴权中心] ❌ 凭证处理流程致命错误: {e}")
        return False

# --- 深度网页嗅探器 (Web Sniffer - Requests版) ---
def sniff_m3u8_from_web(url, ua):
    """
    [兜底逻辑] 模拟 Web Video Caster，使用 requests 高级库进行嗅探
    """
    try:
        headers = {
            'User-Agent': ua,
            'Referer': url,  # 很多网站检查 Referer
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        }
        # verify=False 忽略证书错误，allow_redirects=True 允许跳转
        response = requests.get(url, headers=headers, timeout=15, verify=False, allow_redirects=True)
        response.encoding = response.apparent_encoding # 自动识别编码，防止乱码
        
        html = response.text
        
        # 正则匹配：寻找 http/https 开头，.m3u8 结尾的字符串
        # 兼容转义字符 (例如 \/ -> /)
        pattern = r'(http[s]?:\\?/\\?/[^\s"\'<>]+?\.m3u8[^\s"\'<>]*)'
        matches = re.findall(pattern, html)
        
        if matches:
            # 取第一个匹配项，并处理转义斜杠
            found_url = matches[0].replace('\\/', '/')
            return found_url
    except Exception:
        # requests 的异常我们静默处理
        pass
    return None

# --- 核心解析模块 (混合引擎版) ---
def get_real_url(url, channel_name, retry_mode=False):
    is_yt = 'youtube.com' in url or 'youtu.be' in url
    current_ua = get_random_ua()
    
    # -------------------------------
    # 策略 A: yt-dlp 标准解析
    # -------------------------------
    cmd = ['yt-dlp', '-g', '--no-playlist', '--no-check-certificate', '--user-agent', current_ua]
    
    # 针对 YouTube 强制 HLS，针对通用网站优先 HLS 允许回退
    if is_yt:
        cmd.extend(['-f', 'best[protocol^=m3u8]/best'])
        cmd.extend(['--referer', 'https://www.youtube.com/'])
        if os.path.exists(COOKIE_TEMP_FILE): cmd.extend(['--cookies', COOKIE_TEMP_FILE])
    else:
        # 非油管：尝试通用提取器，移除 mp4 限制，让它自己找
        cmd.extend(['--referer', url])
    
    cmd.append(url)
    
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        if res.returncode == 0:
            raw_output = res.stdout.strip()
            real_url = raw_output.split('\n')[0] if raw_output else None
            if real_url and 'http' in real_url:
                return channel_name, real_url, True
    except:
        pass

    # -------------------------------
    # 策略 B: 深度挖掘 (仅非 YouTube 触发)
    # -------------------------------
    if not is_yt:
        # 如果 yt-dlp 失败，尝试模拟浏览器嗅探 M3U8 (调用 requests 版)
        sniffed_url = sniff_m3u8_from_web(url, current_ua)
        if sniffed_url:
            return channel_name, sniffed_url, True

    return channel_name, None, False

# --- 主程序入口 ---
def update_streams():
    if not os.path.exists(JSON_FILE): return

    # 1. 执行鉴权
    process_smart_cookies()
    
    # 容错读取 JSON
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f: data = json.load(f)
    except Exception as e:
        print(f"❌ JSON 配置文件格式错误: {e}")
        return

    if "Run_Series_Loop" in data:
        data.pop("Run_Series_Loop") 
    
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

    # ==========================================
    # Phase 1: 高优先级 - 直播频道 (Live Channels)
    # ==========================================
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
                        # 检测是否是通过嗅探获取的链接 (简单的逻辑判断)
                        is_sniffed = '.m3u8' in u and 'googlevideo' not in u and 'bilivideo' not in u
                        tag = "🔍 [网页嗅探]" if is_sniffed else "✅ [解析成功]"
                        print(f"   {tag} {n}") 
                        unique_tasks[n] = u
                    else:
                        print(f"   🌪️ [暂缓处理] {n}")
                        orig = next((url for name, url in batch if name == n), None)
                        if orig: failed_channels.append((n, orig))
            time.sleep(0.5)

    # ==========================================
    # Phase 2: 最终挽救 - 全局重试 (Global Retry)
    # ==========================================
    if failed_channels:
        print(f"\n========================================")
        print(f"🔄 [最终挽救] 集中处理所有异常任务...")
        print(f"========================================")
        
        print(f"   >>> 正在修复 {len(failed_channels)} 个直播信号...")
        for idx, (n, u) in enumerate(failed_channels):
            print(f"   🛠️ [正在修复] {n} ...")
            retry_success = False
            for r_attempt in range(1, 3):
                _, new_u, success = get_real_url(u, n, True)
                if success and new_u:
                    print(f"      ✅ [回滚成功] 链路已恢复")
                    unique_tasks[n] = new_u
                    retry_success = True
                    break
                else:
                    time.sleep(2)
            if not retry_success: print(f"      ❌ [最终熔断] 无法接通，已弃用")

    # ==========================================
    # I/O 持久化 (Persistence)
    # ==========================================
    
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
