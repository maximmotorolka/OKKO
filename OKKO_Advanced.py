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
            
            if ws_url and t.get("type") == "page":
                current_origin = "http://localhost:5890"
                if "://" in page_url:
                    if "/app/" in page_url:
                        current_origin = page_url.split("/app/")[0]
                    else:
                        current_origin = "/".join(page_url.split("/")[:3])
                
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
    
    # 💡 核心修改：检测接口是否已经开放
    try:
        requests.get("http://127.0.0.1:9222/json", timeout=1)
        # 🎯 如果走到这里，说明已经有 KOOK 和旧的 okko 守护进程在后台了
        print("[*] 检测到 KOOK 已在后台/托盘运行。")
        
        if os.path.exists(KOOK_PATH):
            print("[*] 正在通过原生客户端唤醒托盘界面...")
            # 🎯 直接运行 KOOK.exe。触发它的单例唤醒机制，让它自己安全地把窗口弹出来并恢复交互！
            subprocess.Popen([KOOK_PATH], creationflags=subprocess.CREATE_NEW_CONSOLE, close_fds=True)
        else:
            print(f"[-] 警告：未在指定目录找到宿主客户端，无法协助呼出窗口。")
            
        # 完成唤醒动作后，当前重复运行的新 okko 进程直接功成身退
        print("[*] 唤醒信号已发送，当前新 okko 进程退出。")
        time.sleep(1)
        sys.exit(0)
        
    except requests.exceptions.RequestException:
        # 如果接口没开，说明是全系统第一次运行，走正常初始化拉起逻辑
        if os.path.exists(KOOK_PATH):
            print("[*] 正在冷启动拉起宿主客户端...")
            cmd = [KOOK_PATH, "--remote-debugging-port=9222", "--remote-allow-origins=*"]
            subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE, close_fds=True)
            is_first_start = True
        else:
            print(f"[-] 严重错误：未在指定目录找到宿主客户端！")
            time.sleep(5)
            return

    # 第一次启动时，利用空档期载入或同步 CSS 规则
    init_css_rules()
    
    if is_first_start:
        print("[*] 正在等待宿主客户端初始化完毕...")
        time.sleep(7)

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
