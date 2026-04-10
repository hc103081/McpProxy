import asyncio
import logging
from typing import Any, Dict, Optional
from .protocol import (
    JsonRpcResponse, 
    MCPInitializeResult, 
    MCPToolListResult, 
    MCPTool, 
    MCPCallToolResult
)
from .config import settings

logger = logging.getLogger(__name__)

class MockMcpClient:
    """
    模擬 MCP 伺服器的客戶端，用於在伺服器不可用時進行開發與測試。
    """
    def __init__(self):
        self._initialized = False
        self._server_capabilities = {"tools": {}}

    async def close(self):
        logger.info("[Mock] 關閉模擬連線")

    async def _send_request(self, method: str, params: Optional[Dict[str, Any]] = None, request_id: int = 1) -> Any:
        """模擬 JSON-RPC 請求處理"""
        logger.info(f"[Mock] 收到請求 -> Method: {method}, ID: {request_id}")
        
        # 模擬網路延遲
        await asyncio.sleep(0.1)

        if method == "initialize":
            return {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "Mock-MCP-Server", "version": "1.0.0-mock"}
            }
        
        elif method == "tools/list":
            return {
                "tools": [
                    {
                        "name": "get_system_info",
                        "description": "獲取系統基本資訊",
                        "inputSchema": {"type": "object", "properties": {}}
                    },
                    {
                        "name": "execute_command",
                        "description": "執行系統指令",
                        "inputSchema": {
                            "type": "object", 
                            "properties": {"cmd": {"type": "string"}}
                        }
                    }
                ]
            }
        
        elif method == "tools/call":
            tool_name = params.get("name") if params else "unknown"
            logger.info(f"[Mock] 呼叫工具: {tool_name}")
            
            if tool_name == "get_system_info":
                return {
                    "content": [{"type": "text", "text": "OS: Windows 11, CPU: Intel i7, RAM: 32GB"}],
                    "isError": False
                }
            elif tool_name == "execute_command":
                cmd = params.get("arguments", {}).get("cmd", "none")
                return {
                    "content": [{"type": "text", "text": f"成功執行指令: {cmd}"}],
                    "isError": False
                }
            else:
                return {
                    "content": [{"type": "text", "text": f"未知工具: {tool_name}"}],
                    "isError": True
                }
        
        else:
            raise Exception(f"Mock 伺服器不支援方法: {method}")

    async def initialize(self):
        logger.info("[Mock] 正在初始化模擬連線...")
        result_data = await self._send_request("initialize")
        result = MCPInitializeResult(**result_data)
        self._initialized = True
        return result

    async def list_tools(self) -> list:
        if not self._initialized:
            await self.initialize()
        result_data = await self._send_request("tools/list")
        result = MCPToolListResult(**result_data)
        return result.tools

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        if not self._initialized:
            await self.initialize()
        params = {"name": name, "arguments": arguments}
        result_data = await self._send_request("tools/call", params=params)
        return MCPCallToolResult(**result_data)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
