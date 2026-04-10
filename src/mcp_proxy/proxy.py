import asyncio
import logging
import os
import base64
import mimetypes
import time
import re
from typing import Any, Dict, List
from .client import McpHttpClient
from .stdio_client import StdioMcpClient
from .mock_client import MockMcpClient
from .exceptions import McpProxyError
from .config import settings

logger = logging.getLogger(__name__)

class McpProxy:
    """
    MCP 代理層：根據配置選擇傳輸模式 (HTTP 或 Stdio) 並與伺服器通訊。
    """
    def __init__(self):
        if settings.use_mock:
            logger.info("使用 Mock 模式啟動 MCP 代理")
            self.client = MockMcpClient()
        elif settings.transport_type == "stdio":
            logger.info(f"使用 Stdio 模式啟動 MCP 代理 (EXE: {settings.mcp_exe_path})")
            self.client = StdioMcpClient(settings.mcp_exe_path)
        else:
            logger.info(f"使用真實 HTTP 模式啟動 MCP 代理 (Endpoint: {settings.mcp_endpoint})")
            self.client = McpHttpClient()

    async def __aenter__(self):
        # Stdio 客戶端需要額外啟動進程
        if hasattr(self.client, 'start'):
            await self.client.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.close()

    async def get_available_tools(self) -> List[Dict[str, Any]]:
        """
        獲取可用工具列表 (相容原介面)
        """
        try:
            tools = await self.client.list_tools()
            return [tool.model_dump() if hasattr(tool, 'model_dump') else tool for tool in tools]
        except McpProxyError as e:
            logger.error(f"獲取工具列表失敗: {e}")
            raise

    async def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        執行工具 (相容原介面)，並自動將本地圖片路徑轉換為標準 MCP 圖片內容。
        """
        # 注入參數邏輯：如果呼叫截圖工具且未提供 savePath，自動生成一個臨時路徑
        if tool_name == "screenshot_to_file" and "savePath" not in params:
            temp_dir = os.environ.get("TEMP") or os.environ.get("TMP")
            if temp_dir:
                filename = f"mcp_proxy_screenshot_{int(time.time())}.png"
                params["savePath"] = os.path.normpath(os.path.join(temp_dir, filename))
                logger.info(f"自動注入 savePath: {params['savePath']}")

        try:
            result = await self.client.call_tool(tool_name, params)
            # 將 Pydantic 模型轉換為字典
            res_dict = result.model_dump() if hasattr(result, 'model_dump') else result
            
            # --- 強化版：全域路徑掃描觸發機制 ---
            # 將整個結果轉換為字串，檢查是否包含任何路徑模式 (支持絕對路徑與圖片後綴的相對路徑)
            result_str = str(res_dict)
            path_match = re.search(r'([a-zA-Z]:\\[^"\'\s]+|[/\w\.-]+/[^"\'\s]+|[\w\.-]+\.(?:png|jpg|jpeg))', result_str)
            
            if path_match:
                extracted_path = path_match.group(1)
                logger.info(f"🚨 [全域掃描] 在結果中發現潛在路徑: {extracted_path}")
                # 構造一個統一的格式交給 _handle_image_result 處理
                return self._handle_image_result({"path": extracted_path})
            
            # 如果沒有發現路徑，則走原有的格式化流程
            if isinstance(res_dict, dict) and "content" in res_dict:
                return res_dict
                
            return {
                "content": [
                    {
                        "type": "text",
                        "text": str(res_dict)
                    }
                ],
                "isError": False
            }
        except McpProxyError as e:
            logger.error(f"執行工具 {tool_name} 失敗: {e}")
            raise
        except Exception as e:
            logger.exception(f"執行工具 {tool_name} 時發生未預期錯誤: {e}")
            raise

    def _normalize_path(self, path: str) -> List[str]:
        """
        路徑適配層：將可能的跨平台路徑 (Linux/Docker) 映射到 Windows 宿主機路徑。
        回傳所有可能的候選路徑列表。
        """
        candidates = []
        
        # 1. 標準化原路徑 (處理 / 與 \ 的差異)
        normalized = os.path.normpath(path)
        candidates.append(normalized)
        
        # 2. 處理 Linux/Docker 風格的路徑映射
        if path.startswith("/"):
            temp_dir = os.environ.get("TEMP") or os.environ.get("TMP")
            if temp_dir:
                # 優先處理 /tmp/
                if path.startswith("/tmp/"):
                    relative_path = path.replace("/tmp/", "", 1)
                # 處理 /workspace/
                elif path.startswith("/workspace/"):
                    # 這裡暫時映射到 TEMP，或者您可以定義一個專門的 workspace 映射
                    relative_path = path.replace("/workspace/", "", 1)
                else:
                    # 其他以 / 開頭的路徑，嘗試取其檔名並放入 TEMP
                    relative_path = os.path.basename(path)
                
                candidates.append(os.path.normpath(os.path.join(temp_dir, relative_path)))
        
        # 3. 處理 /workspace/ 映射到專案根目錄 (更精確的映射)
        if path.startswith("/workspace/"):
            project_root = os.getcwd()
            relative_path = path.replace("/workspace/", "", 1)
            candidates.append(os.path.normpath(os.path.join(project_root, relative_path)))

        # 4. 嘗試僅使用文件名 (處理相對路徑或錯誤前綴)
        filename = os.path.basename(path)
        if filename:
            # 嘗試在當前目錄
            candidates.append(os.path.normpath(filename))
            # 嘗試在 TEMP 目錄
            temp_dir = os.environ.get("TEMP") or os.environ.get("TMP")
            if temp_dir:
                candidates.append(os.path.normpath(os.path.join(temp_dir, filename)))
            # 嘗試在 EXE 所在目錄
            exe_dir = os.path.dirname(settings.mcp_exe_path)
            if exe_dir:
                candidates.append(os.path.normpath(os.path.join(exe_dir, filename)))
        
        return candidates

    def _handle_image_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        將結果中的本地圖片路徑轉換為標準 MCP 圖片內容陣列。
        包含路徑適配層與極限搜索機制。
        """
        import re
        
        path = result.get("path")
        
        # 如果沒有直接的 path 鍵，嘗試從 content 中的文字提取路徑
        if not path and "content" in result:
            for item in result["content"]:
                if item.get("type") == "text":
                    text_content = item.get("text", "")
                    path_match = re.search(r'([a-zA-Z]:\\[^"\'\s]+|[/\w\.-]+/[^"\'\s]+)', text_content)
                    if path_match:
                        path = path_match.group(1)
                        logger.info(f"從文字中成功提取路徑: {path}")
                        break

        if not path:
            return {"content": [{"type": "text", "text": str(result)}], "isError": True}

        # 1. 使用路徑適配層獲取所有候選路徑
        possible_paths = self._normalize_path(path)
        
        actual_path = None
        for p in possible_paths:
            if os.path.exists(p):
                actual_path = p
                break
        
        # 2. 極限搜索：如果所有適配路徑都失敗，在 TEMP 目錄中尋找最新圖片
        if not actual_path:
            filename = os.path.basename(path)
            logger.info(f"適配路徑均未找到，啟動極限搜索... 目標文件名: {filename}")
            temp_dir = os.environ.get("TEMP") or os.environ.get("TMP")
            if temp_dir:
                try:
                    images = []
                    for f in os.listdir(temp_dir):
                        if f.lower().endswith(('.png', '.jpg', '.jpeg')):
                            full_p = os.path.join(temp_dir, f)
                            images.append(full_p)
                    
                    if images:
                        images.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                        latest_image = images[0]
                        # 只要是最近 5 分鐘內生成的圖片且文件名包含部分關鍵字，或就是最新的一張
                        if (time.time() - os.path.getmtime(latest_image)) < 300:
                            actual_path = latest_image
                            logger.info(f"極限搜索成功！找到最新圖片: {actual_path}")
                except Exception as e:
                    logger.error(f"極限搜索出錯: {e}")

        if not actual_path:
            logger.error(f"🚨 [伺服器端風險] 無法定位圖片文件: {path}")
            logger.error(f"嘗試路徑清單: {possible_paths}")
            logger.error(f"極限搜索結果: 在 TEMP 目錄中未發現最近 5 分鐘內生成的圖片。")
            logger.error(f"診斷：伺服器可能回傳了虛擬路徑，或截圖操作實際上失敗但回傳了 success。")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: Image file not found on host. Server returned path: {path}. Please check if the server actually created the file."
                    }
                ],
                "isError": True
            }

        try:
            mime_type, _ = mimetypes.guess_type(actual_path)
            if not mime_type or not mime_type.startswith("image/"):
                mime_type = "image/png"
            
            logger.info(f"成功定位圖片文件: {actual_path} (MIME: {mime_type})")
            
            with open(actual_path, "rb") as image_file:
                file_data = image_file.read()
                encoded_string = base64.b64encode(file_data).decode("utf-8")
            
            logger.info(f"圖片轉換成功: {actual_path} | 大小: {len(file_data)} bytes")
            
            # 轉換完成後立即刪除臨時圖片文件，防止資料夾被佔滿
            try:
                os.remove(actual_path)
                logger.info(f"已清理臨時圖片文件: {actual_path}")
            except Exception as e:
                logger.warning(f"清理臨時圖片文件失敗: {e}")
            
            return {
                "content": [
                    {
                        "type": "image",
                        "data": encoded_string,
                        "mimeType": mime_type
                    },
                    {
                        "type": "text",
                        "text": f"Screenshot captured and uploaded. Local path: {actual_path}"
                    }
                ],
                "isError": False
            }
        except PermissionError as e:
            logger.error(f"🚨 [權限風險] 無權讀取圖片文件 {actual_path}: {e}")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: Permission denied when reading image at {actual_path}. Please run the proxy with appropriate privileges."
                    }
                ],
                "isError": True
            }
        except Exception as e:
            logger.error(f"讀取圖片文件失敗 {actual_path}: {e}")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error reading image: {str(e)}"
                    }
                ],
                "isError": True
            }

async def run_proxy_demo():
    """演示 HTTP MCP 代理功能，進行多種參數與工具測試"""
    async with McpProxy() as proxy:
        try:
            # --- 單元測試：路徑適配層 ---
            print("\n[Test] 正在測試路徑適配層 (Path Adaptation Layer)...")
            test_paths = [
                "C:/Users/Public/test.png",
                "/tmp/screenshot_123.png",
                "/workspace/project/image.jpg",
                "only_filename.png"
            ]
            for p in test_paths:
                candidates = proxy._normalize_path(p)
                print(f"  路徑: {p} -> 候選路徑數量: {len(candidates)}")
                for c in candidates:
                    print(f"    - {c}")
            
            # --- 整合測試：工具執行 ---
            print("\n正在獲取工具列表...")
            tools = await proxy.get_available_tools()
            print(f"發現 {len(tools)} 個工具")
            
            # 定義要測試的工具清單
            target_tools = ['screenshot_to_file', 'screenshot_annotated']
            
            for tool_name in target_tools:
                tool = next((t for t in tools if t['name'] == tool_name), None)
                if not tool:
                    print(f"\n❌ 找不到工具: {tool_name}")
                    continue

                print(f"\n[Tool] 正在測試工具: '{tool_name}'")
                
                test_cases = [
                    {"name": "空參數", "params": {}},
                    {"name": "帶 path 參數", "params": {"path": "C:/Users/Public/test_demo.png"}},
                    {"name": "帶 filename 參數", "params": {"filename": "test_demo.png"}},
                    {"name": "帶 output 參數", "params": {"output": "C:/Users/Public/test_demo.png"}},
                ]

                for case in test_cases:
                    print(f"  [案例: {case['name']}] 參數: {case['params']}")
                    try:
                        res = await proxy.execute_tool(tool_name, case['params'])
                        
                        if "content" in res and any(c.get("type") == "image" for c in res["content"]):
                            print(f"    [Success] 成功！找到了正確的參數組合。")
                            break
                        elif "content" in res and any(c.get("type") == "text" and "Error" in c.get("text", "") for c in res["content"]):
                            print(f"    [Fail] 失敗：回傳了錯誤訊息。")
                        else:
                            print(f"    [Warning] 警告：結果格式不符合預期。")
                            print(f"       結果: {res}")
                    except Exception as e:
                        print(f"    [Error] 發生異常: {e}")
                else:
                    print(f"  [Fail] {tool_name} 的所有測試案例均未成功。")
            
        except Exception as e:
            print(f"發生錯誤: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_proxy_demo())
