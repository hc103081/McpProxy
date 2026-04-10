import asyncio
import register_mcp
import ctypes
import sys
import argparse
import logging
import uvicorn
from src.mcp_proxy.proxy import McpProxy, run_proxy_demo
from src.mcp_proxy.server import McpServer
from src.mcp_proxy.config import settings

def run_as_admin():
    """檢查並嘗試以系統管理員身分重新啟動程式"""
    is_currently_admin = ctypes.windll.shell32.IsUserAnAdmin()
    print(f"[DEBUG] 目前管理員權限狀態: {is_currently_admin}")
    
    if is_currently_admin:
        return True
    else:
        try:
            # 修正: 為每個參數加上雙引號以處理路徑中的空格
            args_quoted = ' '.join([f'"{arg}"' for arg in sys.argv])
            print(f"[DEBUG] 嘗試提升權限，執行指令: {sys.executable} {args_quoted}")
            
            ctypes.windll.shell32.ShellExecuteW(
                None, 
                "runas", 
                sys.executable, 
                args_quoted, 
                None, 
                1
            )
            return False
        except Exception as e:
            print(f"嘗試提升權限時發生錯誤: {e}")
            return False

async def start_server():
    """啟動 MCP 閘道伺服器"""
    print("\n=== 啟動 MCP 閘道伺服器模式 ===")
    server = McpServer()
    
    # 啟動底層 Stdio 代理
    await server.start_proxy()
    
    try:
        config = uvicorn.Config(
            app=server.app, 
            host=settings.server_host, 
            port=settings.server_port, 
            log_level="info"
        )
        server_instance = uvicorn.Server(config)
        await server_instance.serve()
    except Exception as e:
        print(f"伺服器運行出錯: {e}")
    finally:
        await server.stop_proxy()

async def main():
    # 解析參數
    parser = argparse.ArgumentParser(description="McpProxy 啟動程式")
    parser.add_argument("--verbose", action="store_true", help="啟用詳細日誌輸出")
    parser.add_argument("mode", nargs="?", default="client", choices=["client", "server"], help="運行模式: client (測試) 或 server (閘道伺服器)")
    args, unknown = parser.parse_known_args()

    # 設定日誌等級
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    logger = logging.getLogger(__name__)

    # 1. 權限檢查
    is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    
    print("=== McpProxy 系統啟動 ===")
    if args.verbose:
        print("[DEBUG] 詳細模式已啟用")
    
    # 2. 模式分流
    if args.mode == "server":
        # 啟動伺服器模式
        await start_server()
        return

    # --- 以下為原有的 client 測試邏輯 ---
    # 3. 詢問是否需要執行本地 COM 註冊
    do_register = input("是否需要執行本地 COM 服務註冊? (y/n): ").lower() == 'y'
    if do_register:
        if not is_admin:
            print("註冊功能需要管理員權限，正在請求提升...")
            if not run_as_admin():
                sys.exit(0)
        
        print("執行本地註冊...")
        register_mcp.main()
        print("註冊流程完成。")

    # 4. 啟動 HTTP MCP 代理服務
    print("\n啟動 HTTP MCP 代理連線至 https://hc103081.servehttp.com/ ...")
    try:
        await run_proxy_demo()
    except Exception as e:
        print(f"HTTP MCP 執行失敗: {e}")
    
    print("\n" + "="*40)
    input("流程已完成，請按下 Enter 鍵結束程式...")

if __name__ == "__main__":
    asyncio.run(main())
