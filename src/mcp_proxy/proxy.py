import asyncio
import logging
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
        執行工具 (相容原介面)
        """
        try:
            result = await self.client.call_tool(tool_name, params)
            return result.model_dump() if hasattr(result, 'model_dump') else result
        except McpProxyError as e:
            logger.error(f"執行工具 {tool_name} 失敗: {e}")
            raise

async def run_proxy_demo():
    """演示 HTTP MCP 代理功能"""
    async with McpProxy() as proxy:
        try:
            print("正在獲取工具列表...")
            tools = await proxy.get_available_tools()
            print(f"發現 {len(tools)} 個工具: {[t['name'] for t in tools]}")
            
            if tools:
                first_tool = tools[0]
                print(f"嘗試呼叫工具: {first_tool['name']}...")
                # 這裡假設工具接受空參數，實際應根據 inputSchema 決定
                res = await proxy.execute_tool(first_tool['name'], {})
                print(f"執行結果: {res}")
                
        except Exception as e:
            print(f"發生錯誤: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_proxy_demo())
