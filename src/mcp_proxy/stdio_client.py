import asyncio
import logging
import os
import sys
from typing import Any, Dict, Optional
from .protocol import (
    JsonRpcRequest, JsonRpcResponse, JsonRpcError,
    MCPInitializeRequest, MCPInitializeResult,
    MCPToolListResult, MCPCallToolRequest, MCPCallToolResult
)
from .exceptions import McpProtocolError, McpRemoteError
from .config import settings

logger = logging.getLogger(__name__)

class StdioMcpClient:
    """
    MCP Stdio 客戶端：透過標準輸入/輸出 (stdin/stdout) 與 MCP 伺服器通訊。
    """
    def __init__(self, exe_path: str):
        self.exe_path = exe_path
        self.process: Optional[asyncio.subprocess.Process] = None
        self._initialized = False
        self._server_capabilities: Optional[Dict[str, Any]] = None

    async def start(self):
        """啟動 MCP 伺服器進程"""
        logger.info(f"正在啟動 MCP 伺服器進程: {self.exe_path}")
        try:
            self.process = await asyncio.create_subprocess_exec(
                self.exe_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            logger.info("MCP 伺服器進程已啟動")
        except Exception as e:
            logger.error(f"啟動 MCP 伺服器失敗: {e}")
            raise

    async def close(self):
        """關閉伺服器進程"""
        if self.process:
            logger.info("正在關閉 MCP 伺服器進程...")
            self.process.terminate()
            await self.process.wait()
            logger.info("MCP 伺服器已關閉")

    async def _send_request(self, method: str, params: Optional[Dict[str, Any]] = None, request_id: int = 1) -> Any:
        """透過 stdin 發送 JSON-RPC 請求並從 stdout 讀取回應 (包含過濾非 JSON 日誌)"""
        if not self.process:
            raise RuntimeError("伺服器進程尚未啟動")

        request_body = JsonRpcRequest(
            method=method,
            params=params,
            id=request_id
        ).model_dump()
        
        import json
        payload = json.dumps(request_body) + "\n"
        
        logger.debug(f"發送 Stdio 請求 -> Method: {method}, ID: {request_id}")
        self.process.stdin.write(payload.encode())
        await self.process.stdin.drain()

        # 循環讀取直到找到有效的 JSON 回應
        while True:
            line = await self.process.stdout.readline()
            if not line:
                raise McpProtocolError("伺服器未回傳任何數據 (EOF)")

            decoded_line = line.decode().strip()
            if not decoded_line:
                continue
            
            # MCP Stdio 協定：只有以 '{' 開頭的行才是 JSON-RPC 訊息
            if decoded_line.startswith('{'):
                try:
                    data = json.loads(decoded_line)
                    logger.debug(f"收到 Stdio 回應: {data}")
                    rpc_response = JsonRpcResponse(**data)
                    break
                except Exception as e:
                    logger.warning(f"跳過無效 JSON 行: {decoded_line} | 錯誤: {e}")
            else:
                # 這裡捕捉到的是伺服器誤寫到 stdout 的日誌 (例如 info: Microsoft.Hosting...)
                logger.debug(f"跳過伺服器日誌行: {decoded_line}")

        if rpc_response.error:
            raise McpRemoteError(
                rpc_response.error.code, 
                rpc_response.error.message, 
                rpc_response.error.data
            )

        return rpc_response.result

    async def initialize(self):
        """執行 MCP 初始化握手"""
        logger.info("正在執行 Stdio 初始化握手...")
        params = MCPInitializeRequest().model_dump()
        result_data = await self._send_request("initialize", params=params)
        
        result = MCPInitializeResult(**result_data)
        self._initialized = True
        logger.info(f"Stdio MCP 初始化成功。伺服器版本: {result.protocolVersion}")
        return result

    async def list_tools(self) -> list:
        """獲取可用工具列表"""
        if not self._initialized:
            await self.initialize()
            
        result_data = await self._send_request("tools/list")
        result = MCPToolListResult(**result_data)
        logger.info(f"StdioClient: 從伺服器接收到 {len(result.tools)} 個工具")
        return result.tools

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """呼叫指定工具"""
        if not self._initialized:
            await self.initialize()
            
        params = MCPCallToolRequest(name=name, arguments=arguments).model_dump()
        result_data = await self._send_request("tools/call", params=params)
        
        return MCPCallToolResult(**result_data)

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
