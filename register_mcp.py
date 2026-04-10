import os
import sys
import ctypes
import winreg
import logging
import uuid
from datetime import datetime

# ================= 配置區域 =================
EXE_PATH = r"C:\tools\Orbination\Orbination-AI-Desktop-Vision-Control\DesktopControlMcp\bin\Release\net8.0-windows10.0.22621.0\DesktopControlMcp.exe"
PROG_ID = "DesktopControlMcp.Service"
# 使用固定 CLSID 以確保一致性，或使用 uuid.uuid4() 生成
CLSID = "{A1B2C3D4-E5F6-4A7B-8C9D-0E1F2A3B4C5D}" 
SERVICE_NAME = "DesktopControlMcp Service"
LOG_FILE = "mcp_registration.log"
# ===========================================

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

def is_admin():
    """檢查是否以系統管理員權限執行"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except AttributeError:
        return False

def check_file_exists(path):
    """檢查目標執行檔是否存在"""
    if os.path.exists(path):
        logging.info(f"目標執行檔存在: {path}")
        return True
    else:
        logging.error(f"目標執行檔不存在: {path}")
        return False

def register_com_component():
    """執行 COM 註冊邏輯"""
    try:
        # 1. 註冊 CLSID
        clsid_key_path = rf"CLSID\{CLSID}"
        with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, clsid_key_path) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, SERVICE_NAME)
            logging.info(f"成功建立 CLSID 鍵: {clsid_key_path}")

        # 2. 註冊 LocalServer32 (針對 EXE)
        local_server_path = rf"CLSID\{CLSID}\LocalServer32"
        with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, local_server_path) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, EXE_PATH)
            logging.info(f"成功建立 LocalServer32 鍵: {local_server_path}")

        # 3. 註冊 ProgID
        with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, PROG_ID) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, CLSID)
            logging.info(f"成功建立 ProgID 鍵: {PROG_ID}")

        return True
    except PermissionError:
        logging.error("權限不足！請以『系統管理員』身分執行此腳本。")
        return False
    except Exception as e:
        logging.error(f"註冊過程中發生未知錯誤: {e}")
        return False

def verify_registration():
    """驗證 MCP 註冊是否生效"""
    try:
        # 驗證 ProgID 是否指向正確的 CLSID
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, PROG_ID) as key:
            val, _ = winreg.QueryValueEx(key, "")
            if val == CLSID:
                logging.info(f"驗證成功: ProgID {PROG_ID} 正確指向 {CLSID}")
            else:
                logging.warning(f"驗證失敗: ProgID {PROG_ID} 指向 {val}，而非 {CLSID}")
                return False

        # 驗證 LocalServer32 是否指向正確的路徑
        local_server_path = rf"CLSID\{CLSID}\LocalServer32"
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, local_server_path) as key:
            val, _ = winreg.QueryValueEx(key, "")
            if val == EXE_PATH:
                logging.info(f"驗證成功: LocalServer32 正確指向 {EXE_PATH}")
            else:
                logging.warning(f"驗證失敗: LocalServer32 指向 {val}，而非 {EXE_PATH}")
                return False

        return True
    except FileNotFoundError:
        logging.error("驗證失敗: 找不到相關的登錄檔鍵值。")
        return False
    except Exception as e:
        logging.error(f"驗證過程中發生錯誤: {e}")
        return False

def main():
    logging.info("=== MCP 自動化註冊腳本啟動 ===")
    
    # 1. 權限檢查
    if not is_admin():
        logging.error("此腳本必須以系統管理員權限執行。")
        print("\n請右鍵點擊終端機或 IDE，選擇『以系統管理員身分執行』後再次嘗試。")
        sys.exit(1)

    # 2. 檔案檢查
    if not check_file_exists(EXE_PATH):
        sys.exit(1)

    # 3. 執行註冊
    logging.info("開始註冊 MCP 服務...")
    if register_com_component():
        logging.info("註冊操作完成。")
    else:
        logging.error("註冊操作失敗。")
        sys.exit(1)

    # 4. 驗證結果
    logging.info("開始驗證註冊狀態...")
    if verify_registration():
        logging.info("=== MCP 註冊成功且驗證通過！ ===")
    else:
        logging.error("=== MCP 註冊完成但驗證失敗，請檢查日誌。 ===")
        sys.exit(1)

if __name__ == "__main__":
    main()
