<div align="center">

<pre style="font-family: 'Courier New', monospace; background-color: #0d1117; color: #3fb950; border: 4px solid #1f2428; border-radius: 15px; padding: 20px; box-shadow: 0 0 20px rgba(63, 185, 80, 0.4); text-align: left; width: fit-content; margin: 0 auto;">
  _______________________________________________________
 |                                                       |
 |   .-----------------------------------------------.   |
 |   |      ___  ____  ____                          |   |
 |   |     / _ \/ ___|| __ )                         |   |
 |   |    | | | \___ \|  _ \    >> STATUS: ONLINE    |   |
 |   |    | |_| |___) | |_) |   >> CORE: PYTHON_3    |   |
 |   |     \___/|____/|____/    >> MODE: AUTO_PILOT  |   |
 |   |                                               |   |
 |   |   -----------------------------------------   |   |
 |   |   >> TERMINAL: OSB_SYSTEM_V1.0                |   |
 |   |   >> PROTOCOL: HLS_LIVE_STREAM                |   |
 |   '-----------------------------------------------'   |
 |                                                       |
 |    [ON/OFF]  [MENU]  [VOL+]  [VOL-]  [CH+]  [CH-]     |
 |_______________________________________________________|
      /_\                                     /_\
</pre>

<br>

<h1 style="color: #3fb950; font-family: monospace; letter-spacing: 2px;">OPEN SOURCE BROADCASTER (OSB)</h1>
<h3 style="color: #8b949e;">全自动化直播源抓取与分发系统 · Termux 专用版</h3>

<p>
  <img src="https://img.shields.io/badge/CORE-PYTHON_3.10-yellow?style=for-the-badge&logo=python&logoColor=black" alt="Python">
  <img src="https://img.shields.io/badge/HOST-TERMUX_ANDROID-green?style=for-the-badge&logo=android&logoColor=white" alt="Termux">
  <img src="https://img.shields.io/badge/STREAM-HLS_M3U8-red?style=for-the-badge&logo=youtube&logoColor=white" alt="HLS">
  <img src="https://img.shields.io/badge/DEPLOY-GITHUB_GIT-blue?style=for-the-badge&logo=github&logoColor=white" alt="Git">
</p>

</div>

---

## 📺 系统简介 (SYSTEM_LOG)

> <samp>Initializing system core... Connection established.</samp>

本项目是一个基于 **Termux + Python** 的全自动化直播源维护系统。它运行在 Android 手机本地环境，利用物理设备的真实 IP 绕过云端风控，自动解析 YouTube、Twitch、Bilibili 等平台的直播流，并生成永久可用的 `.m3u8` 列表同步至 GitHub。

### ⚡ 核心机能 (KERNEL FEATURES)

| 模块 | 功能描述 | 技术细节 |
| :--- | :--- | :--- |
| **📡 智能抓取** | 自动解析真实流地址 | 基于 `yt-dlp` 内核，支持多平台 (YT/B站/Twitch) |
| **🍪 Cookie 转换** | 自动处理身份验证 | **Auto-Netscape**: 自动将浏览器 `F12` 原始 Cookie 转为 Netscape 格式 |
| **📂 无限分类** | 支持嵌套 JSON 结构 | 递归解析 `streams.json`，支持无限层级文件夹分类 |
| **🔄 无感替换** | 仅更新失效链接 | **In-Place Update**: 绝不修改 M3U8 的标题、Logo、分组信息 |
| **🤖 异步守护** | 7x24小时自动化 | 双脚本架构：`auto_run.sh` (守护) + `run_now.sh` (插队触发) |

---

## 🛠️ 调台指南 (CONFIGURATION)

<details open>
<summary><strong>📡 1. 频道映射数据库 (streams.json)</strong></summary>

这是控制中心的数据库。你可以随意使用嵌套的大括号 `{}` 来分类，脚本会自动递归读取。

**文件位置:** `./streams.json`

```json
{
  "油管影视剧频道": {
    "24H憨豆先生": "[https://www.youtube.com/watch?v=lldsi8ItNaI](https://www.youtube.com/watch?v=lldsi8ItNaI)"
  },
  "油管动画频道": {
    "24H猫和老鼠": "[https://www.youtube.com/live/rEKifG2XUZg](https://www.youtube.com/live/rEKifG2XUZg)",
    "24H海绵宝宝": "[https://www.youtube.com/live/NC5JgC4FDCw](https://www.youtube.com/live/NC5JgC4FDCw)"
  },
  "哔哩哔哩动画直播": {
    "24H海绵宝宝": "[https://live.bilibili.com/14495324](https://live.bilibili.com/14495324)"
  }
}

> ⚠️ 极其重要: JSON 中的链接必须是纯文本字符串（如上所示），不能包含 Markdown 的 []() 格式，否则脚本会报错！
> 
</details>
<details>
<summary><strong>📺 2. 播放列表模板 (TV.m3u8)</strong></summary>
这是最终生成的节目单。你需要先手动创建这个文件，配置好你喜欢的 LOGO 和分组。链接处可以是旧链接或任意占位符。
文件位置: ./TV.m3u8
#EXTM3U

### --- 分组：油管动画 --- ###
#EXTINF:-1 tvg-logo="[https://logo.url/jerry.png](https://logo.url/jerry.png)" group-title="动画",24H猫和老鼠
http://replace_me_automatically

### --- 分组：B站直播 --- ###
#EXTINF:-1 group-title="Bilibili",24H海绵宝宝
http://wait_for_update

> 原理: 脚本读取 #EXTINF 行末尾的名字，去 JSON 里找对应的源。命中后，只替换下一行的链接，其他信息保持不动。
> 
</details>
<details>
<summary><strong>🔐 3. 身份验证 (cookies.txt)</strong></summary>
用于通过 YouTube 的 429 限流或 Sign 验证。本系统内置了自动转换模块。
 * 电脑浏览器按 F12 打开开发者工具 -> Network。
 * 刷新 YouTube 页面，找到任意请求，复制 Request Headers 里的 Cookie: 后面的长字符串。
 * 新建 cookies.txt，直接粘贴 进去。
 * 脚本运行时会自动生成 cookies_netscape.txt 给下载器使用。
</details>
🕹️ 控制台指令 (CONTROLS)
在 Termux 终端中操作。建议开启 Termux 的 Acquire wakelock 防止系统杀后台。
▶️ 启动自动挂机 (AUTO-PILOT)
启动守护进程，进入每小时自动循环。
cd /sdcard/live
sh auto_run.sh

<samp style="color: green;">> System: 任务完成，进入 1 小时倒计时...</samp>
⏩ 手动插队更新 (TRIGGER NOW)
如果你刚改了 JSON 想立刻生效，无需重启主程序，新建一个窗口运行：
cd /sdcard/live
sh run_now.sh

<samp style="color: orange;">> System: ⚡ 检测到手动触发信号！跳过等待，立即运行！</samp>
💾 文件结构 (SCHEMATICS)
/live
├── auto_run.sh          # [核心] 进程守护脚本 (循环/Git同步/倒计时)
├── run_now.sh           # [遥控] 信号发射脚本 (用于手动触发)
├── update.py            # [核心] Python 业务逻辑
├── streams.json         # [配置] 源头数据库
├── cookies.txt          # [配置] 原始 Cookie
├── TV.m3u8              # [产物] 最终播放列表
└── no sex/              # [分流] 其他分类文件夹
    └── TV_1(no sex).m3u8

<div align="center">


<p style="color: #8b949e; font-size: 12px;">
⚠ DISCLAIMER

本仓库仅供技术研究与个人学习使用。

The author is not responsible for any misuse of this software.

Project initialized: 2026 | Location: Berlin/CyberSpace
</p>
</div>

