import time
import requests
import json
import os
import sys
import subprocess
from websocket import create_connection

# 💡 1. 远程 GitHub 规则地址
GITHUB_CSS_URL = "https://raw.githubusercontent.com/NoC486/OKKO/refs/heads/main/style.css"

# 💡 2. 精准定位当前运行的目录
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 💡 3. 自动定位同目录下的 CSS 和【上一级目录】的大写 KOOK.exe
CSS_PATH = os.path.join(BASE_DIR, "style.css")
KOOK_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "KOOK.exe"))

# 全局变量，用于在内存中缓存清洗后的注入代码
CACHED_JS_CODE = ""

def init_css_rules():
    """仅在启动时运行一次。优先从云端拉取，失败则读取本地，并缓存到内存中"""
    global CACHED_JS_CODE
    css_content = ""
    
    try:
        print("[*] 正在启动首次云端规则同步...")
        response = requests.get(GITHUB_CSS_URL, timeout=3)
        if response.status_code == 200:
            css_content = response.text
            print("[+] 首次云端同步成功！")
            try:
                with open(CSS_PATH, "w", encoding="utf-8") as f:
                    f.write(css_content)
            except Exception:
                pass
    except Exception as e:
        print(f"[-] 首次云端同步遭遇网络波动: {e}")

    # 如果联网失败，降级读取本地
    if not css_content:
        if os.path.exists(CSS_PATH):
            print("[*] 正在启用本地备份的 style.css 规则...")
            with open(CSS_PATH, "r", encoding="utf-8") as f:
                css_content = f.read()
        else:
            print("[-] 严重警告：云端拉取失败且本地无备份文件，本次运行将缺乏去广告规则！")
            return

    # 将样式清洗并封装
    css = css_content.replace("\n", " ").replace('"', '\\"')
    CACHED_JS_CODE = f'if(!window.__ad_rules_loaded){{const s = document.createElement("style"); s.textContent = "{css}"; document.head.appendChild(s); window.__ad_rules_loaded=true;}}'

def check_kook_process_alive():
    """检测 Windows 系统中 KOOK.exe 是否还在运行"""
    try:
        output = subprocess.check_output('tasklist /FI "IMAGENAME eq KOOK.exe"', shell=True).decode('gbk', errors='ignore')
        if "KOOK.exe" in output:
            return True
    except Exception:
        pass
    return False

def inject_to_kook():
    """自适应 Origin 注入函数"""
    global CACHED_JS_CODE
    if not CACHED_JS_CODE:
        return False

    try:
        res = requests.get("http://127.0.0.1:9222/json", timeout=2).json()
        injected = False
        
        for t in res:
            ws_url = t.get("webSocketDebuggerUrl")
            page_url = t.get("url", "")
            
            # 只有当类型是 page 且能拿到 webSocketDebuggerUrl 时才处理
            if ws_url and t.get("type") == "page":
                # 🌟 核心优化：动态解析当前页面的真实 Origin（完美兼容 /app/ 后面跟任意路径的情况）
                current_origin = "http://localhost:5890"  # 默认保底值
                if "://" in page_url:
                    if "/app/" in page_url:
                        # 比如从 http://localhost:5888/app/channels 提取出 http://localhost:5888
                        current_origin = page_url.split("/app/")[0]
                    else:
                        # 兜底：如果连 /app/ 都没有，则直接切前三段
                        current_origin = "/".join(page_url.split("/")[:3])
                
                try:
                    ws = create_connection(
                        ws_url, 
                        timeout=2,
                        suppress_origin=True,
                        header=[f"Origin: {current_origin}"]  # 🎯 动态填入提取出的真实 Origin
                    )
                    ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": CACHED_JS_CODE}}))
                    ws.send(json.dumps({"id": 2, "method": "Page.addScriptToEvaluateOnNewDocument", "params": {"source": CACHED_JS_CODE}}))
                    ws.close()
                    injected = True
                except Exception:
                    continue
        return injected
    except Exception:
        return False

def main():
    print("[*] OKKO 增强盾启动...")
    print(f"[*] 预设宿主路径: {KOOK_PATH}")
    
    init_css_rules()
    
    # 首次拉起托管
    try:
        requests.get("http://127.0.0.1:9222/json", timeout=1)
        is_first_start = False
    except requests.exceptions.RequestException:
        if os.path.exists(KOOK_PATH):
            print("[*] 正在拉起宿主客户端...")
            cmd = [KOOK_PATH, "--remote-debugging-port=9222", "--remote-allow-origins=*"]
            subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE, close_fds=True)
            is_first_start = True
            time.sleep(8)
        else:
            print(f"[-] 严重错误：未在指定目录找到宿主客户端！")
            time.sleep(5)
            return

    while True:
        if not is_first_start and not check_kook_process_alive():
            print("[*] 检测到宿主客户端已关闭，插件正在退出...")
            sys.exit(0)
            
        success = inject_to_kook()
        if success:
            is_first_start = False
            print("[*] 规则注入成功，看守中...")
            
        time.sleep(10)

if __name__ == "__main__":
    main()
