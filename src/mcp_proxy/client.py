import asyncio
import logging
import httpx
from typing import Any, Dict, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .protocol import (
    JsonRpcRequest, JsonRpcResponse, JsonRpcError,
    MCPInitializeRequest, MCPInitializeResult,
    MCPToolListResult, MCPCallToolRequest, MCPCallToolResult
)
from .exceptions import McpHttpError, McpProtocolError, McpRemoteError, McpTimeoutError
from .config import settings

logger = logging.getLogger(__name__)

class McpHttpClient:
    def __init__(self):
        self.endpoint = settings.mcp_endpoint.rstrip('/')
        self.client = httpx.AsyncClient(
            timeout=settings.request_timeout,
            headers={
                "User-Agent": settings.user_agent,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Strict-Transport-Security": "max-age=31536000; includeSubDomains"
            }
        )
        self._initialized = False
        self._server_capabilities: Optional[Dict[str, Any]] = None

    async def close(self):
        await self.client.aclose()

    @retry(
        stop=stop_after_attempt(settings.max_retries),
        wait=wait_exponential(multiplier=settings.retry_backoff_factor, min=1, max=10),
        retry=retry_if_exception_type((httpx.RequestError, McpTimeoutError)),
        reraise=True
    )
    async def _send_request(self, method: str, params: Optional[Dict[str, Any]] = None, request_id: int = 1) -> Any:
        """底層 JSON-RPC 請求發送邏輯"""
        request_body = JsonRpcRequest(
            method=method,
            params=params,
            id=request_id
        ).model_dump()

        logger.debug(f"發送 MCP 請求 -> Method: {method}, ID: {request_id}, Payload: {request_body}")
        
        start_time = asyncio.get_event_loop().time()
        try:
            response = await self.client.post(self.endpoint, json=request_body)
            elapsed = asyncio.get_event_loop().time() - start_time
            logger.debug(f"收到 MCP 回應 <- 耗時: {elapsed:.3f}s, 狀態碼: {response.status_code}")
            
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP 狀態錯誤: {e.response.status_code} - {e.response.text}")
            raise McpHttpError(e.response.status_code, e.response.text)
        except httpx.TimeoutException:
            logger.error(f"請求伺服器逾時 (Timeout: {settings.request_timeout}s)")
            raise McpTimeoutError("請求伺服器逾時")
        except httpx.RequestError as e:
            logger.error(f"網路請求失敗 (無法建立連線): {str(e)}")
            # 修正: 不要將連線失敗誤報為 HTTP 500，改用 0 或特定的連線錯誤碼
            raise McpHttpError(0, f"網路請求失敗 (Connection Failed): {str(e)}")

        try:
            data = response.json()
            logger.debug(f"回應內容: {data}")
            rpc_response = JsonRpcResponse(**data)
        except Exception as e:
            logger.error(f"解析 JSON-RPC 回應失敗: {str(e)}")
            raise McpProtocolError(f"解析 JSON-RPC 回應失敗: {str(e)}")

        if rpc_response.error:
            logger.error(f"伺服器回傳 JSON-RPC 錯誤: {rpc_response.error}")
            raise McpRemoteError(
                rpc_response.error.code, 
                rpc_response.error.message, 
                rpc_response.error.data
            )

        return rpc_response.result

    async def initialize(self):
        """執行 MCP 初始化握手"""
        logger.info("正在初始化 MCP 連線...")
        params = MCPInitializeRequest().model_dump()
        result_data = await self._send_request("initialize", params=params)
        
        result = MCPInitializeResult(**result_data)
        self._server_capabilities = result.capabilities
        self._initialized = True
        logger.info(f"MCP 初始化成功。伺服器版本: {result.protocolVersion}")
        return result

    async def list_tools(self) -> list:
        """獲取可用工具列表"""
        if not self._initialized:
            await self.initialize()
            
        result_data = await self._send_request("tools/list")
        result = MCPToolListResult(**result_data)
        return result.tools

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """呼叫指定工具"""
        if not self._initialized:
            await self.initialize()
            
        params = MCPCallToolRequest(name=name, arguments=arguments).model_dump()
        result_data = await self._send_request("tools/call", params=params)
        
        return MCPCallToolResult(**result_data)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
