import os
import sys
import subprocess
import signal
import time
import logging
import urllib.request
import zipfile
import asyncio
import shutil
import ctypes
import webbrowser
import threading
from typing import List

# Try to import pystray and PIL for the system tray
try:
    import pystray
    from PIL import Image, ImageDraw
    PYS_TRAY_AVAILABLE = True
except ImportError:
    PYS_TRAY_AVAILABLE = False

# Configure logging
log_file = "system.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8")
    ]
)
logger = logging.getLogger("Launcher")

def is_admin():
    """ 檢查目前是否以管理員權限執行 """
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def hide_console():
    """ 隱藏控制台視窗，實現真正的背景運行 """
    if sys.platform == 'win32':
        try:
            kernel32 = ctypes.windll.kernel32
            user32 = ctypes.windll.user32
            hWnd = kernel32.GetConsoleWindow()
            if hWnd:
                user32.ShowWindow(hWnd, 0) # SW_HIDE
                logger.info("控制台視窗已隱藏，程式進入背景運行模式。")
        except Exception as e:
            logger.warning(f"隱藏控制台失敗: {e}")

def get_resource_path(relative_path: str) -> str:
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def download_caddy():
    """ Downloads Caddy binary if not present """
    caddy_exe = os.path.join(os.getcwd(), "caddy.exe")
    if os.path.exists(caddy_exe):
        return caddy_exe

    logger.info("正在下載 Caddy 伺服器...")
    url = "https://github.com/caddyserver/caddy/releases/download/v2.8.4/caddy_2.8.4_windows_amd64.zip"
    zip_path = "caddy.zip"
    
    try:
        urllib.request.urlretrieve(url, zip_path)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(".")
        os.remove(zip_path)
        logger.info("Caddy 下載並解壓縮成功。")
        return caddy_exe
    except Exception as e:
        logger.error(f"下載 Caddy 失敗: {e}")
        sys.exit(1)

def kill_existing_caddy():
    """ 關閉所有現有的 caddy 進程，防止端口衝突 (尤其是 2019 管理端口) """
    logger.info("正在清理現有的 Caddy 進程...")
    try:
        subprocess.run(["taskkill", "/F", "/IM", "caddy.exe"], 
                       capture_output=True, text=True)
    except Exception as e:
        logger.warning(f"清理 Caddy 進程時發生錯誤 (可能目前沒有運行中的 Caddy): {e}")

def start_process(command: List[str], name: str):
    """ Starts a process and returns the Popen object """
    logger.info(f"正在啟動 {name}...")
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        logger.info(f"{name} 已啟動 (PID: {process.pid})")
        return process
    except Exception as e:
        logger.error(f"啟動 {name} 失敗: {e}")
        sys.exit(1)

def monitor_process_output(proc: subprocess.Popen):
    """ 獨立線程：監控單個進程的輸出 """
    try:
        for line in iter(proc.stdout.readline, ''):
            if line:
                logger.info(f"[{proc.pid}] {line.strip()}")
    except Exception as e:
        logger.error(f"監控進程 {proc.pid} 輸出時發生錯誤: {e}")

def monitor_processes(processes: List[subprocess.Popen]):
    """ 監控所有進程是否仍在運行 """
    # 為每個進程啟動一個輸出監控線程
    for proc in processes:
        t = threading.Thread(target=monitor_process_output, args=(proc,), daemon=True)
        t.start()

    while True:
        for proc in processes:
            if proc.poll() is not None:
                logger.error(f"進程 {proc.pid} 已意外停止 (Exit Code: {proc.returncode})")
                return False
        time.sleep(1)
    return True

async def run_internal_server():
    """ Wrapper to run the MCP server logic """
    try:
        from main import start_server
        await start_server()
    except Exception as e:
        logger.error(f"伺服器運行出錯: {e}")
        sys.exit(1)

class TrayIconManager:
    """ 系統托盤圖標管理類 """
    def __init__(self, processes_ref):
        self.processes = processes_ref

    def create_image(self):
        """ 創建一個簡單的圖標 (藍色圓形) """
        width, height = 64, 64
        image = Image.new('RGB', (width, height), (30, 41, 59)) # Slate-800
        dc = ImageDraw.Draw(image)
        dc.ellipse([10, 10, 54, 54], fill=(59, 130, 246)) # Blue-500
        return image

    def open_dashboard(self, icon, item):
        logger.info("打開管理控制台...")
        webbrowser.open("http://localhost:8082")

    def restart_services(self, icon, item):
        logger.info("請求重啟服務...")
        os._exit(0)

    def exit_app(self, icon, item):
        logger.info("正在從托盤退出程序...")
        icon.stop()
        for proc in self.processes:
            proc.terminate()
        os._exit(0)

    def run(self):
        if not PYS_TRAY_AVAILABLE:
            logger.warning("pystray 或 Pillow 未安裝，無法啟動系統托盤圖標。")
            return

        icon = pystray.Icon("McpProxy")
        icon.icon = self.create_image()
        icon.title = "McpProxy Gateway"
        icon.menu = pystray.Menu(
            pystray.MenuItem("打開管理控制台", self.open_dashboard),
            pystray.MenuItem("重啟服務", self.restart_services),
            pystray.MenuItem("退出程式", self.exit_app)
        )
        
        logger.info("系統托盤圖標已啟動。")
        icon.run()

def main():
    # --- 內部模式：僅運行 MCP Server ---
    if len(sys.argv) > 1 and sys.argv[1] == "--internal-server":
        try:
            asyncio.run(run_internal_server())
        except KeyboardInterrupt:
            pass
        return

    # --- 外部模式：啟動所有服務 ---
    # 0. 隱藏控制台視窗，實現背景運行
    hide_console()

    # 0.1 權限檢查 (Caddy 綁定 80/443 端口需要管理員權限)
    if not is_admin():
        logger.warning("⚠️ 警告：目前未以管理員權限執行。Caddy 可能會因為無法綁定 80/443 端口而啟動失敗。")
        logger.info("建議：請嘗試『右鍵 -> 以系統管理員身分執行』。")

    # 0.1 清理舊進程 (防止端口 2019 衝突)
    kill_existing_caddy()

    # 1. 處理 Caddy 執行檔
    caddy_exe = get_resource_path("caddy.exe")
    if not os.path.exists(caddy_exe):
        caddy_exe = download_caddy()
    
    # 2. 處理 Caddyfile (將其從打包路徑複製到當前工作目錄，避免路徑問題)
    bundled_caddyfile = get_resource_path("Caddyfile")
    cwd_caddyfile = os.path.join(os.getcwd(), "Caddyfile")
    
    try:
        if os.path.exists(bundled_caddyfile):
            shutil.copy2(bundled_caddyfile, cwd_caddyfile)
            logger.info(f"已將 Caddyfile 部署至工作目錄: {cwd_caddyfile}")
        elif not os.path.exists(cwd_caddyfile):
            logger.error(f"找不到 Caddyfile (打包路徑與工作目錄均無): {bundled_caddyfile}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"部署 Caddyfile 失敗: {e}")
        sys.exit(1)

    # 3. 準備啟動命令
    server_cmd = [sys.executable, "--internal-server"]
    caddy_cmd = [caddy_exe, "run", "--config", cwd_caddyfile]

    processes = []
    try:
        # 啟動 MCP Server
        server_proc = start_process(server_cmd, "MCP Server")
        processes.append(server_proc)
        
        # 啟動 Caddy
        caddy_proc = start_process(caddy_cmd, "Caddy Proxy")
        processes.append(caddy_proc)
        
        # 啟動系統托盤圖標 (在獨立線程中運行)
        tray = TrayIconManager(processes)
        tray_thread = threading.Thread(target=tray.run, daemon=True)
        tray_thread.start()
        
        logger.info("=== 所有服務已啟動，正在監控輸出 ===")
        if not monitor_processes(processes):
            logger.error("其中一個服務停止運行，正在關閉所有服務...")
            
    except KeyboardInterrupt:
        logger.info("接收到停止信號，正在關閉服務...")
    finally:
        for proc in processes:
            logger.info(f"正在停止進程 {proc.pid}...")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        logger.info("所有服務已關閉。")

if __name__ == "__main__":
    main()
