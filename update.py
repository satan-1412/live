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

# 屏蔽证书警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 伪装池：专门针对不同类型的网站
UA_POOL = {
    # 模拟安卓手机（最容易获取直链）
    "Android": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    # 模拟苹果手机
    "iOS": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    # 模拟电脑
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

# ==========================================
# 🕸️ 核弹级网页嗅探器 (Nuclear Sniffer)
# ==========================================

def clean_and_validate(url):
    """
    清洗器：把各种变态的转义字符还原成人类能看的 URL
    例如：http:\/\/ -> http://
    """
    try:
        # 1. 处理 JSON 风格的反斜杠转义 (http:\/\/...)
        url = url.replace(r'\/', '/')
        # 2. 处理 URL 编码 (http%3A%2F%2F...)
        if '%' in url:
            url = urllib.parse.unquote(url)
        # 3. 处理 Unicode 转义 (\u002F)
        if '\\u' in url:
            url = url.encode('utf-8').decode('unicode_escape')
        
        url = url.strip()
        
        # 再次检查头部，防止解出来是 // 开头的相对路径
        if url.startswith('//'):
            url = 'https:' + url
            
        # 验证是否为有效链接
        if url.startswith('http') and ('.m3u8' in url or '.flv' in url or 'm3u8?' in url):
            return url
    except:
        pass
    return None

def find_m3u8_deep(text):
    """
    [核心算法] 正则核弹：不放过任何一个像链接的字符串
    """
    candidates = []
    
    # ⚡ 正则 1: 标准或转义的 http 链接 (捕捉 http:// 和 http:\/\/ 和 http%3A%2F%2F)
    # 解释：https? 后面跟着 (冒号 或 %3A) 然后是 (斜杠 或 %2F 或 反斜杠) 重复两次
    pattern_universal = r'(https?[:%3A\\]+[\/%2F\\]+[^"\s\'<>{}|\\^`]+?\.m3u8[^"\s\'<>{}|\\^`]*)'
    matches = re.findall(pattern_universal, text, re.I)
    candidates.extend(matches)
    
    # ⚡ 正则 2: 专门针对山东卫视 iqilu 的特征 (tstreamlive)
    # 即使它不以 .m3u8 结尾，只要包含这个核心域名且看起来像个长链接，也抓出来看看
    if 'iqilu.com' in text or 'tstreamlive' in text:
        pattern_iqilu = r'(https?[:\\]+[\/\\].+?tstreamlive.+?\.m3u8[^"\s\'<>]*)'
        matches_iqilu = re.findall(pattern_iqilu, text, re.I)
        candidates.extend(matches_iqilu)

    # 清洗并返回第一个可用的
    for u in candidates:
        clean_url = clean_and_validate(u)
        if clean_url:
            return clean_url
            
    return None

def sniff_single_ua(url, ua, depth=0):
    """单次嗅探逻辑 (支持 iframe 穿透)"""
    if depth > 1: return None 

    try:
        headers = {
            'User-Agent': ua,
            'Referer': url,
            # 增加 Accept 头，假装自己是很懂的浏览器
            'Accept': 'text/html,application/xhtml+xml,application/json,text/javascript,*/*;q=0.01',
            'X-Requested-With': 'XMLHttpRequest' # 假装是 AJAX 请求，诱骗服务器吐出 JSON
        }
        
        response = requests.get(url, headers=headers, timeout=12, verify=False, allow_redirects=True)
        response.encoding = response.apparent_encoding 
        text = response.text
        
        # 1. 🔍 暴力搜索当前页面的所有角落
        found_url = find_m3u8_deep(text)
        if found_url: return found_url

        # 2. 📡 扫描内嵌窗口 (Iframe) -> 钻进去找
        if depth == 0: # 只钻一层，防止死循环
            iframe_pattern = r'<iframe[^>]+src=["\']([^"\']+)["\']'
            iframes = re.findall(iframe_pattern, text, re.I)
            
            for iframe_src in iframes:
                full_iframe_url = urllib.parse.urljoin(url, iframe_src)
                if 'ad' in full_iframe_url or 'google' in full_iframe_url: continue
                
                # 递归调用
                deep_found = sniff_single_ua(full_iframe_url, ua, depth + 1)
                if deep_found: return deep_found

    except Exception:
        pass
    return None

# --- 核心解析模块 ---
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
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
            if res.returncode == 0:
                raw = res.stdout.strip().split('\n')[0]
                if raw and 'http' in raw: return channel_name, raw, True
        except: pass
        return channel_name, None, False
    
    # -------------------------------
    # 策略 B: 网站轮询嗅探 (非油管)
    # -------------------------------
    else:
        # 1. 先试安卓 (概率最高)
        url_android = sniff_single_ua(url, UA_POOL["Android"])
        if url_android: return channel_name, url_android, True
        
        # 2. 再试电脑 (有些老网站只认电脑)
        url_pc = sniff_single_ua(url, UA_POOL["PC"])
        if url_pc: return channel_name, url_pc, True

        # 3. 实在不行，祭出 yt-dlp 试试运气
        cmd = ['yt-dlp', '-g', '--no-playlist', '--no-check-certificate', '--user-agent', UA_POOL["Android"]]
        cmd.append(url)
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if res.returncode == 0:
                raw = res.stdout.strip().split('\n')[0]
                if raw and 'http' in raw: return channel_name, raw, True
        except: pass

    return channel_name, None, False

# --- 主程序入口 ---
def update_streams():
    if not os.path.exists(JSON_FILE): return

    process_smart_cookies()
    
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f: data = json.load(f)
    except Exception as e:
        print(f"❌ JSON 格式错误: {e}")
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
                        tag = "✅ [解析成功]"
                        if '.m3u8' in u and 'googlevideo' not in u: tag = "🔍 [网页嗅探]"
                        print(f"   {tag} {n}") 
                        unique_tasks[n] = u
                    else:
                        print(f"   🌪️ [暂缓处理] {n}")
                        orig = next((url for name, url in batch if name == n), None)
                        if orig: failed_channels.append((n, orig))
            time.sleep(0.5)

    # Phase 2: 重试
    if failed_channels:
        print(f"\n========================================")
        print(f"🔄 [最终挽救] 集中处理所有异常任务...")
        print(f"========================================")
        
        for idx, (n, u) in enumerate(failed_channels):
            print(f"   🛠️ [正在修复] {n} ...")
            retry_success = False
            # 重试只跑一次，避免浪费时间
            _, new_u, success = get_real_url(u, n, True)
            if success and new_u:
                print(f"      ✅ [回滚成功] 链路已恢复")
                unique_tasks[n] = new_u
                retry_success = True
            
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
