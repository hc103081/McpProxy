import os
import sys

def get_resource_path(relative_path: str) -> str:
    """ 
    獲取資源的絕對路徑，兼容開發環境與 PyInstaller 打包環境。
    PyInstaller 會將資源解壓到 sys._MEIPASS 臨時目錄中。
    """
    try:
        # PyInstaller 運行時會定義 _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # 開發環境下使用當前工作目錄
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)
