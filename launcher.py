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
from typing import List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("Launcher")

def is_admin():
    """ 檢查目前是否以管理員權限執行 """
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def kill_existing_caddy():
    """ 關閉所有現有的 caddy 進程，防止端口衝突 (尤其是 2019 管理端口) """
    logger.info("正在清理現有的 Caddy 進程...")
    try:
        # 使用 taskkill 強制關閉所有名為 caddy.exe 的進程
        subprocess.run(["taskkill", "/F", "/IM", "caddy.exe"], 
                       capture_output=True, text=True)
    except Exception as e:
        logger.warning(f"清理 Caddy 進程時發生錯誤 (可能目前沒有運行中的 Caddy): {e}")

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

def monitor_processes(processes: List[subprocess.Popen]):
    """ Monitors processes and prints their output in real-time """
    while True:
        for proc in processes:
            if proc.poll() is not None:
                # 嘗試讀取最後幾行日誌以診斷錯誤
                remaining_output = proc.stdout.read()
                logger.error(f"進程 {proc.pid} 已意外停止 (Exit Code: {proc.returncode})")
                if remaining_output:
                    logger.error(f"最後日誌輸出:\n{remaining_output}")
                return False
            
            line = proc.stdout.readline()
            if line:
                logger.info(f"[{proc.pid}] {line.strip()}")
        
        time.sleep(0.1)
    return True

async def run_internal_server():
    """ Wrapper to run the MCP server logic """
    try:
        from main import start_server
        await start_server()
    except Exception as e:
        logger.error(f"伺服器運行出錯: {e}")
        sys.exit(1)

def main():
    # --- 內部模式：僅運行 MCP Server ---
    if len(sys.argv) > 1 and sys.argv[1] == "--internal-server":
        try:
            asyncio.run(run_internal_server())
        except KeyboardInterrupt:
            pass
        return

    # --- 外部模式：啟動所有服務 ---
    # 0. 權限檢查 (Caddy 綁定 80/443 端口需要管理員權限)
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
