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

# ⚠️ 浏览器模式比较吃内存，并发建议调小一点 (5-8之间)
BATCH_SIZE = 5  

# ==========================================
# 🕵️‍♂️ 浏览器驱动嗅探 (Selenium Sniffer)
# ==========================================
def sniff_via_browser(url):
    """
    [重武器] 启动无头浏览器进行嗅探
    仅用于：yt-dlp 搞不定的非 YouTube 网站 (如 iqilu.com)
    """
    driver = None
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        
        options = Options()
        options.add_argument("--headless") # 无头模式
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        # 伪装成手机，逼迫网站交出 m3u8
        options.add_argument("user-agent=Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")

        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(25) # 设置超时
        
        driver.get(url)
        time.sleep(4) # 等待 JS 执行 (如 token 计算)
        
        # 1. 暴力搜源码
        page_source = driver.page_source
        matches = re.findall(r'(http[s]?://[^\s"\'<>]+?\.m3u8[^\s"\'<>]*)', page_source)
        if matches:
            return matches[0].replace('\\/', '/')
            
        # 2. 搜 video 标签
        try:
            video = driver.find_element(By.TAG_NAME, 'video')
            src = video.get_attribute('src')
            if src and 'm3u8' in src: return src
        except: pass

    except:
        pass
    finally:
        if driver:
            try: driver.quit()
            except: pass
    return None

# --- 核心解析模块 (智能分流版) ---
def get_real_url(url, channel_name):
    # ==========================================
    # 策略 A: YouTube 专属快速通道
    # ==========================================
    # 逻辑：yt-dlp 是油管的神。它不行就是源挂了，不必再试浏览器。
    if 'youtube.com' in url or 'youtu.be' in url:
        cmd = ['yt-dlp', '-g', '--no-playlist', '--no-check-certificate', '-f', 'best[protocol^=m3u8]/best', url]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            if res.returncode == 0:
                raw = res.stdout.strip().split('\n')[0]
                if raw and 'http' in raw:
                    return channel_name, raw, True
        except: pass
        # 油管失败直接返回失败，跳过浏览器环节
        return channel_name, None, False

    # ==========================================
    # 策略 B: 普通网站 (混合双打)
    # ==========================================
    else:
        # 1. 先试 yt-dlp (轻量级，速度快)
        cmd = ['yt-dlp', '-g', '--referer', url, url]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                raw = res.stdout.strip().split('\n')[0]
                if raw and 'http' in raw:
                    return channel_name, raw, True
        except: pass

        # 2. 失败了？启动浏览器 (重武器兜底)
        # 仅针对非 YouTube 的顽固分子 (如山东卫视)
        # 这里不打印额外日志，保持界面整洁，只在成功时显示
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
        
        # ⚠️ 并发不宜过大，防止浏览器启动过多卡死手机
        for i in range(0, len(live_tasks), BATCH_SIZE):
            batch = live_tasks[i:i+BATCH_SIZE]
            print(f"\n⚡ [批次执行] 序列: {i//BATCH_SIZE + 1}...")

            with ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
                futures = {executor.submit(get_real_url, u, n): n for n, u in batch}
                for future in as_completed(futures):
                    n, u, success = future.result()
                    if success and u:
                        # 区分一下来源，稍微给点提示，但不破坏队形
                        tag = "✅ [解析成功]"
                        if '.m3u8' in u and 'googlevideo' not in u and 'youtube' not in u:
                            # 如果不是油管链接但成功了，多半是浏览器抓到的
                            pass 
                        print(f"   {tag} {n}") 
                        unique_tasks[n] = u
                    else:
                        print(f"   🌪️ [暂缓处理] {n}")
                        orig = next((url for name, url in batch if name == n), None)
                        if orig: failed_channels.append((n, orig))
            time.sleep(0.5)

    # Phase 2: 重试 (仅做最后挣扎，不建议重试时再开浏览器，太慢)
    if failed_channels:
        print(f"\n========================================")
        print(f"🔄 [最终挽救] 集中处理所有异常任务...")
        print(f"========================================")
        
        for idx, (n, u) in enumerate(failed_channels):
            print(f"   🛠️ [正在修复] {n} ...")
            # 简单重试，不再调用浏览器，防止死循环卡住
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
