import json
import subprocess
import os
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================
# ⚙️ 系统核心配置
# ==========================================
TARGET_FILES = ['TV.m3u8', 'no sex/TV_1(no sex).m3u8']
JSON_FILE = 'streams.json'

# ⚠️ 浏览器模式极耗内存，并发必须压低，否则 Termux 会炸
BATCH_SIZE = 4

# ==========================================
# 🕵️‍♂️ 浏览器网络嗅探 (Network Sniffer)
# ==========================================
def sniff_via_browser(url):
    """
    [上帝模式] 启动浏览器并监听网络流量
    模拟 Web Video Caster 的核心原理：拦截 m3u8 请求
    """
    driver = None
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

        # 1. 配置开启网络日志 (Performance Logging)
        # 这是捕捉隐藏流的关键！
        caps = DesiredCapabilities.CHROME
        caps['goog:loggingPrefs'] = {'performance': 'ALL'}

        options = Options()
        options.add_argument("--headless") # 无头模式
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        # 伪装成安卓手机，诱导网站加载 H5 播放器
        options.add_argument("user-agent=Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")

        # 启动浏览器
        driver = webdriver.Chrome(options=options) # Selenium 4.x 不需要 desired_capabilities 参数，日志默认开启或通过 options 配置
        
        # 开启 CDP (Chrome DevTools Protocol) 监听网络
        driver.execute_cdp_cmd('Network.enable', {})

        driver.set_page_load_timeout(30)
        driver.get(url)
        
        # 2. 模拟用户行为：点击屏幕尝试触发播放
        time.sleep(3)
        try:
            # 尝试点击 body 或 video 标签，模拟手指触屏
            driver.find_element(By.TAG_NAME, 'body').click()
            driver.execute_script("document.querySelector('video').play();")
        except: pass
        
        # 再等几秒让请求发出去
        time.sleep(5)

        # 3. 🔍 核心：扫描网络日志 (The God Mode)
        # 获取浏览器所有的网络请求记录
        logs = driver.get_log('performance')
        
        for entry in logs:
            message = json.loads(entry['message'])['message']
            
            # 筛选网络请求
            if message['method'] == 'Network.requestWillBeSent':
                req_url = message['params']['request']['url']
                
                # 🎯 命中目标：发现 m3u8
                if '.m3u8' in req_url:
                    # 排除掉广告或者无效的
                    if 'ad' not in req_url and 'http' in req_url:
                        return req_url

            # 备选：有时候是在 response 里
            elif message['method'] == 'Network.responseReceived':
                resp_url = message['params']['response']['url']
                if '.m3u8' in resp_url:
                    return resp_url

    except Exception:
        # 浏览器启动失败或超时，静默处理
        pass
    finally:
        if driver:
            try: driver.quit()
            except: pass
    return None

# --- 核心解析模块 (智能分流) ---
def get_real_url(url, channel_name):
    # ==========================================
    # 策略 A: YouTube 专属快速通道 (yt-dlp)
    # ==========================================
    if 'youtube.com' in url or 'youtu.be' in url:
        cmd = ['yt-dlp', '-g', '--no-playlist', '--no-check-certificate', '-f', 'best[protocol^=m3u8]/best', url]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            if res.returncode == 0:
                raw = res.stdout.strip().split('\n')[0]
                if raw and 'http' in raw:
                    return channel_name, raw, True
        except: pass
        return channel_name, None, False

    # ==========================================
    # 策略 B: 普通网站 (混合双打)
    # ==========================================
    else:
        # 1. 先试 yt-dlp (轻量级)
        cmd = ['yt-dlp', '-g', '--referer', url, url]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                raw = res.stdout.strip().split('\n')[0]
                if raw and 'http' in raw:
                    return channel_name, raw, True
        except: pass

        # 2. 失败了？启动浏览器网络嗅探 (重武器)
        # 只有这里才会打印一行灰色调试信息，让你知道它在努力
        print(f"   ⚙️ [启动嗅探] {channel_name} ...")
        
        sniffed = sniff_via_browser(url)
        if sniffed:
            return channel_name, sniffed, True

    return channel_name, None, False

# --- 主程序入口 ---
def update_streams():
    if not os.path.exists(JSON_FILE): return
    
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f: data = json.load(f)
    except: return

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
        
        # 批量执行
        for i in range(0, len(live_tasks), BATCH_SIZE):
            batch = live_tasks[i:i+BATCH_SIZE]
            print(f"\n⚡ [批次执行] 序列: {i//BATCH_SIZE + 1}...")

            with ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
                futures = {executor.submit(get_real_url, u, n): n for n, u in batch}
                for future in as_completed(futures):
                    n, u, success = future.result()
                    if success and u:
                        # 文本风格严格保留，不管是怎么抓到的，都显示解析成功
                        print(f"   ✅ [解析成功] {n}") 
                        unique_tasks[n] = u
                    else:
                        print(f"   🌪️ [暂缓处理] {n}")
                        orig = next((url for name, url in batch if name == n), None)
                        if orig: failed_channels.append((n, orig))
            time.sleep(0.5)

    # Phase 2: 重试 (仅 yt-dlp 快速重试，不再开浏览器)
    if failed_channels:
        print(f"\n========================================")
        print(f"🔄 [最终挽救] 集中处理所有异常任务...")
        print(f"========================================")
        
        for idx, (n, u) in enumerate(failed_channels):
            print(f"   🛠️ [正在修复] {n} ...")
            if 'youtube' in u:
                cmd = ['yt-dlp', '-g', u]
                try:
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                    if res.returncode == 0 and 'http' in res.stdout:
                        print(f"      ✅ [回滚成功] 链路已恢复")
                        unique_tasks[n] = res.stdout.strip()
                        continue
                except: pass
            
            print(f"      ❌ [最终熔断] 无法接通，已弃用")

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
