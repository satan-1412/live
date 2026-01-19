# -*- coding: utf-8 -*-
"""
IPTV PRO 终极奇点版 (V42.0 Singularity)
------------------------------------------------------
[技术极限堆料]
1. HLS 动态中间人 (MITM): 实时下载并重写 m3u8，欺骗播放器以为是本地流。
2. 302 分片重定向: 视频分片不走代理流量，而是精确计算后 302 到 Google。
3. 双模解析引擎: 同时支持 yt-dlp 原生接口和 HLS 提取接口。
4. 内存级缓存: 毫秒级响应，防止被 Google 封锁。
5. 伪装层: 注入 VLC/ExoPlayer 专用头部，伪装 User-Agent。
"""

import os
import time
import json
import random
import threading
import subprocess
import urllib.parse
import socket
import re
import requests
from flask import Flask, Response, redirect, request, abort

# ==========================================
# ⚙️ 核心配置 (Core Config)
# ==========================================
TXT_DB_DIR = "TXT"
PORT = 10000
CACHE_TTL = 280  # 链接有效期通常为 6 小时，但为了安全我们 5 分钟刷新一次
REQUEST_TIMEOUT = 10

# 伪装指纹池
UA_POOL = {
    'ios': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1',
    'android': 'Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.193 Mobile Safari/537.36',
    'tv': 'Mozilla/5.0 (SMART-TV; Linux; Tizen 2.4.0) AppleWebkit/538.1 (KHTML, like Gecko) SamsungBrowser/1.0 TV Safari/538.1',
    'vlc': 'VLC/3.0.18 LibVLC/3.0.18',
    'exo': 'ExoPlayerLib/2.18.1'
}

app = Flask(__name__)

# ==========================================
# 🧠 内存数据库 (In-Memory DB)
# ==========================================
class MemoryDB:
    """高速缓存层，减少磁盘 IO 和 API 调用"""
    _cache = {}
    _lock = threading.Lock()

    @classmethod
    def get(cls, key):
        with cls._lock:
            data = cls._cache.get(key)
            if data:
                if time.time() < data['expire']:
                    return data['val']
                else:
                    del cls._cache[key]
        return None

    @classmethod
    def set(cls, key, val, ttl=CACHE_TTL):
        with cls._lock:
            cls._cache[key] = {
                'val': val,
                'expire': time.time() + ttl
            }

# ==========================================
# 🕵️‍♂️ 赛博解析器 (Cyber Solver)
# ==========================================
class CyberSolver:
    @staticmethod
    def get_real_url(vid_id, mode='hls'):
        """
        暴力解析视频真实地址
        mode: 'hls' (返回 .m3u8) | 'mp4' (返回 .mp4 直链)
        """
        # 1. 查缓存
        cache_key = f"{vid_id}_{mode}"
        cached = MemoryDB.get(cache_key)
        if cached: return cached

        url = f"https://www.youtube.com/watch?v={vid_id}"
        print(f"⚡ [解析] 正在破解: {vid_id} (模式: {mode})")

        # 2. 定义攻击策略
        strategies = []
        if mode == 'hls':
            strategies = [
                # 策略 A: iOS 伪装 (获取 Master HLS)
                ['yt-dlp', '-g', '-f', 'best[protocol^=m3u8]', '--user-agent', UA_POOL['ios'], url],
                # 策略 B: 通用 HLS
                ['yt-dlp', '-g', '-f', 'b', url] 
            ]
        else:
            strategies = [
                # 策略 C: Android MP4 (最稳直链)
                ['yt-dlp', '-g', '-f', 'best[ext=mp4]', '--user-agent', UA_POOL['android'], url],
                # 策略 D: 兜底 MP4
                ['yt-dlp', '-g', '-f', '18/22', url]
            ]

        # 3. 执行攻击
        for cmd in strategies:
            try:
                # 增加重试参数
                res = subprocess.run(
                    cmd, 
                    capture_output=True, 
                    text=True, 
                    timeout=15,
                    encoding='utf-8'
                )
                if res.returncode == 0:
                    real_url = res.stdout.strip().split('\n')[0]
                    if real_url.startswith('http'):
                        MemoryDB.set(cache_key, real_url)
                        return real_url
            except Exception as e:
                print(f"   ⚠️ 策略失败: {e}")
                continue
        
        return None

# ==========================================
# 📝 M3U8 重写引擎 (Manifest Rewriter)
# ==========================================
class ManifestRewriter:
    """
    核心黑科技：下载远程 m3u8，把里面的链接替换成本地代理链接
    """
    @staticmethod
    def process_playlist(remote_url, vid_id):
        try:
            # 1. 下载远程 M3U8
            # 必须带上 iOS UA，否则 Google 可能返回 403
            headers = {'User-Agent': UA_POOL['ios']}
            resp = requests.get(remote_url, headers=headers, timeout=10, verify=False)
            if resp.status_code != 200:
                print(f"❌ 获取远程列表失败: {resp.status_code}")
                return None
            
            original_content = resp.text
            new_lines = []
            
            # 2. 逐行重写
            # 目标：把 https://googlevideo.com/... 变成 http://127.0.0.1/chunk/...?url=...
            for line in original_content.split('\n'):
                line = line.strip()
                if not line: continue
                
                if line.startswith('#'):
                    new_lines.append(line)
                else:
                    # 这是一个分片链接 (Chunk URL)
                    # 我们对其进行 URL 编码，作为参数传给我们的 Chunk Proxy
                    encoded_url = urllib.parse.quote(line)
                    # 构造本地代理链接
                    # 欺骗播放器：加上 .ts 后缀
                    local_proxy = f"http://127.0.0.1:{PORT}/chunk/{vid_id}.ts?remote={encoded_url}"
                    new_lines.append(local_proxy)
            
            return "\n".join(new_lines)
            
        except Exception as e:
            print(f"❌ 重写引擎崩溃: {e}")
            return None

# ==========================================
# 🛠️ 辅助工具
# ==========================================
def load_channel_data(short_id):
    try:
        path = os.path.join(TXT_DB_DIR, f"{short_id}.txt")
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f: 
                return json.load(f)
    except: pass
    return None

@app.after_request
def apply_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# ==========================================
# 🚦 路由控制器 (Routes)
# ==========================================

# 1. 播放列表入口 (Entry Point)
@app.route('/<mode>/<short_id>/playlist.m3u8')
def serve_playlist(mode, short_id):
    """
    返回给播放器的“主菜单”。
    """
    data = load_channel_data(short_id)
    if not data: return Response("Channel Not Found", status=404)
    
    episodes = data['episodes']
    
    # 构造 M3U8 头部
    m3u8_lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        "#EXT-X-ALLOW-CACHE:NO",
        # 欺骗播放器：注入 VLC 专用 UA
        f"#EXTVLCOPT:http-user-agent={UA_POOL['ios']}" 
    ]
    
    # 逻辑分流
    target_eps = []
    if mode == 'random':
        target_eps = [random.choice(episodes)] # 随机抽一个
        # 随机模式不声明 VOD，让播放器以为是直播流，从而不仅度条缓存
    else:
        target_eps = episodes
        m3u8_lines.append("#EXT-X-PLAYLIST-TYPE:VOD")
        # 计算最大时长
        max_dur = max([e.get('duration', 10) for e in episodes])
        m3u8_lines.append(f"#EXT-X-TARGETDURATION:{int(max_dur) + 5}")

    print(f"📄 [请求] 列表: {data['meta']['name']} (模式: {mode})")

    # 生成列表体
    for i, ep in enumerate(target_eps):
        if mode == 'vod' and i > 0:
            m3u8_lines.append("#EXT-X-DISCONTINUITY") # 关键：告诉播放器这里断开了
        
        title = ep.get('title', 'Unknown')
        dur = ep.get('duration', 0)
        vid = ep['id']
        
        m3u8_lines.append(f"#EXTINF:{dur},{title}")
        # 关键：指向我们的 HLS 代理接口
        # 链接末尾伪装成 index.m3u8
        m3u8_lines.append(f"http://127.0.0.1:{PORT}/hls_proxy/{vid}/index.m3u8")
    
    if mode == 'vod':
        m3u8_lines.append("#EXT-X-ENDLIST")

    return Response("\n".join(m3u8_lines), mimetype='application/vnd.apple.mpegurl')

# 2. HLS 代理接口 (The Proxy)
@app.route('/hls_proxy/<vid_id>/index.m3u8')
def hls_proxy(vid_id):
    """
    这是播放器请求的“二级列表”。
    我们会在这里进行“偷天换日”。
    """
    # 尝试获取 HLS 直链
    real_url = CyberSolver.get_real_url(vid_id, mode='hls')
    
    if not real_url:
        # 如果 HLS 失败，尝试降级到 MP4 (302 跳转)
        print(f"⚠️ HLS 获取失败，降级为 MP4 跳转: {vid_id}")
        mp4_url = CyberSolver.get_real_url(vid_id, mode='mp4')
        if mp4_url:
            return redirect(mp4_url, code=302)
        else:
            return Response("Link fetch failed", status=503)

    # 启动重写引擎
    rewritten_m3u8 = ManifestRewriter.process_playlist(real_url, vid_id)
    
    if rewritten_m3u8:
        print(f"✅ [重写] 成功伪造 HLS 列表: {vid_id}")
        return Response(rewritten_m3u8, mimetype='application/vnd.apple.mpegurl')
    else:
        # 如果重写失败（可能是 Google 没返回 m3u8），直接 302 到原始链接碰运气
        return redirect(real_url, code=302)

# 3. 分片重定向接口 (Chunk Redirect)
@app.route('/chunk/<vid_id>.ts')
def chunk_redirect(vid_id):
    """
    这是最底层的分片请求。
    参数 remote 包含了真实的 Google 链接。
    我们直接 302 踢过去。
    """
    remote_url = request.args.get('remote')
    if not remote_url: return abort(400)
    
    # 解码 URL
    # remote_url = urllib.parse.unquote(remote_url) # Flask request.args 自动解码，通常不需要再解
    
    # 302 跳转 (Cloud Link)
    # 播放器会直接去连 Google，不消耗本地流量
    return redirect(remote_url, code=302)

if __name__ == '__main__':
    # 环境自检
    if not os.path.exists(TXT_DB_DIR): os.makedirs(TXT_DB_DIR)
    
    # 禁用 urllib3 警告
    import urllib3
    urllib3.disable_warnings()
    
    print("\n" + "="*60)
    print(f" ☢️  IPTV PRO 终极奇点版 (V42.0 Singularity)")
    print(f" 🛡️  技术栈: HLS重写 + 302分片 + 智能伪装")
    print(f" 📡  服务端口: {PORT}")
    print("="*60 + "\n")
    
    app.run(host='0.0.0.0', port=PORT, threaded=True, debug=False)
