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

def load_and_cache_css(css_content):
    """将 CSS 样式清洗并封装进全局 JS 缓存"""
    global CACHED_JS_CODE
    css = css_content.replace("\n", " ").replace('"', '\\"')
    CACHED_JS_CODE = f'if(!window.__ad_rules_loaded){{const s = document.createElement("style"); s.textContent = "{css}"; document.head.appendChild(s); window.__ad_rules_loaded=true;}}'

def init_css_rules():
    """本地优先规则：本地有则直接用（秒开），没有则去云端拉取"""
    if os.path.exists(CSS_PATH):
        print("[+] 检测到本地存在 style.css，正在直接载入规则（加速启动）...")
        try:
            with open(CSS_PATH, "r", encoding="utf-8") as f:
                css_content = f.read()
            load_and_cache_css(css_content)
            return
        except Exception as e:
            print(f"[-] 读取本地 style.css 失败: {e}，将尝试云端获取...")

    print("[*] 本地未找到规则文件，正在尝试从云端同步...")
    try:
        response = requests.get(GITHUB_CSS_URL, timeout=4)
        if response.status_code == 200:
            css_content = response.text
            print("[+] 云端规则同步成功！")
            load_and_cache_css(css_content)
            try:
                with open(CSS_PATH, "w", encoding="utf-8") as f:
                    f.write(css_content)
                print("[+] 已将云端规则保存至本地，下次启动将实现秒开。")
            except Exception:
                pass
            return
    except Exception as e:
        print(f"[-] 云端拉取遭遇网络波动: {e}")

    print("[-] 严重警告：本地无文件且云端获取失败，本次运行将缺乏去广告规则！")

def is_kook_ui_ready():
    """仅检测检测应用核心 UI 是否已经加载出来，不做任何注入"""
    try:
        res = requests.get("http://127.0.0.1:9222/json", timeout=1).json()
        for t in res:
            page_url = t.get("url", "")
            if t.get("webSocketDebuggerUrl") and t.get("type") == "page":
                if "/app/" in page_url:
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
            
            if ws_url and t.get("type") == "page":
                if "/app/" not in page_url:
                    continue
                
                current_origin = "http://localhost:5890"
                if "://" in page_url:
                    current_origin = page_url.split("/app/")[0]
                
                try:
                    ws = create_connection(
                        ws_url, 
                        timeout=2,
                        suppress_origin=True,
                        header=[f"Origin: {current_origin}"]
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
    print("[*] OKKO 增强盾 启动...")
    print(f"[*] 预设宿主路径: {KOOK_PATH}")
    
    # 检测接口是否已经开放
    try:
        requests.get("http://127.0.0.1:9222/json", timeout=1)
        print("[*] 检测到 KOOK 已在后台/托盘运行。")
        
        if os.path.exists(KOOK_PATH):
            print("[*] 正在通过原生客户端唤醒托盘界面...")
            subprocess.Popen([KOOK_PATH], creationflags=subprocess.CREATE_NEW_CONSOLE, close_fds=True)
        else:
            print(f"[-] 警告：未在指定目录找到宿主客户端，无法协助呼出窗口。")
            
        print("[*] 唤醒信号已发送，当前新 okko 进程退出。")
        time.sleep(1)
        sys.exit(0)
        
    except requests.exceptions.RequestException:
        if os.path.exists(KOOK_PATH):
            print("[*] 正在冷启动拉起宿主客户端...")
            cmd = [KOOK_PATH, "--remote-debugging-port=9222", "--remote-allow-origins=*"]
            subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE, close_fds=True)
        else:
            print(f"[-] 严重错误：未在指定目录找到宿主客户端！")
            time.sleep(5)
            return

    # 第一次启动时，载入或同步 CSS 规则
    init_css_rules()
    
    # 🎯 核心逻辑重构：双重保险
    print("[*] 正在侦测 KOOK 主界面渲染状态...")
    while True:
        if is_kook_ui_ready():
            # 🔔 找到了主界面！此时 KOOK 刚刚渲染完主 DOM。
            # 为了防止干扰它加载底层 C++ node 模块，我们在这里原地安全等待 4 秒钟
            print("[+] 检测到应用主界面已现身，为确保原生模块安全加载，稳健等待 4 秒...")
            time.sleep(4)
            break
        time.sleep(1) # 降低冷启动时的探测频率（每秒只查一次，不给主进程制造压力）
            
    # 安全期满，果断进场单次注入
    if inject_to_kook():
        print("[+] 广告规则已成功无痕注入！")
    else:
        print("[-] 提示：未找到满足条件的注入目标。")
            
    print("[*] OKKO 任务已安全完成，进程优雅退出。")
    time.sleep(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
