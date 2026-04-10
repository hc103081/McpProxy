import asyncio
import logging
import uuid
from typing import Any, Dict, Optional
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

from .proxy import McpProxy
from .config import settings
from .exceptions import McpProxyError

logger = logging.getLogger(__name__)

# 儲存每個 session 的訊息隊列，用於將結果推送到 SSE 流
session_queues: Dict[str, asyncio.Queue] = {}

class McpMessage(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Optional[Any] = None

class McpServer:
    def __init__(self):
        self.app = FastAPI(title="MCP Proxy Gateway")
        
        # 允許所有跨域請求，解決 Claude/Open WebUI 的連線問題
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        self.proxy: Optional[McpProxy] = None
        self._setup_routes()

    def _setup_routes(self):
        @self.app.get("/sse")
        async def sse_endpoint(request: Request):
            """
            建立 SSE 連線，並告知客戶端發送訊息的端點。
            """
            session_id = str(uuid.uuid4())
            queue = asyncio.Queue()
            session_queues[session_id] = queue
            
            logger.info(f"新 SSE 連線建立: {session_id}")

            async def event_generator():
                try:
                    # 1. 根據 MCP 規範，首先發送 endpoint 事件
                    yield {
                        "event": "endpoint",
                        "data": f"/messages?sessionId={session_id}"
                    }
                    
                    # 2. 持續監聽隊列，並定期發送心跳以維持連線
                    while True:
                        if await request.is_disconnected():
                            break
                        
                        try:
                            # 等待訊息，但設置超時以發送心跳
                            data = await asyncio.wait_for(queue.get(), timeout=15.0)
                            yield {
                                "event": "message",
                                "data": data
                            }
                        except asyncio.TimeoutError:
                            # 發送心跳包 (空註釋)，防止隧道工具因閒置而切斷連線
                            yield {
                                "event": "ping",
                                "data": "keep-alive"
                            }
                finally:
                    logger.info(f"SSE 連線關閉: {session_id}")
                    session_queues.pop(session_id, None)

            return EventSourceResponse(
                event_generator(),
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no", # 禁用 Nginx/Caddy 緩衝
                }
            )

        @self.app.post("/messages")
        async def messages_endpoint(request: Request, sessionId: str):
            """
            接收客戶端的 JSON-RPC 請求並轉發給 MCP 伺服器。
            """
            if sessionId not in session_queues:
                raise HTTPException(status_code=404, detail="Session not found")

            try:
                body = await request.json()
                mcp_msg = McpMessage(**body)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid JSON-RPC request: {str(e)}")

            try:
                result = None
                if mcp_msg.method == "initialize":
                    res = await self.proxy.client.initialize()
                    result = res.model_dump() if hasattr(res, 'model_dump') else res
                elif mcp_msg.method == "tools/list":
                    res = await self.proxy.get_available_tools()
                    # get_available_tools 已經回傳 list[dict]，直接使用
                    result = {"tools": res}
                elif mcp_msg.method == "tools/call":
                    params = mcp_msg.params or {}
                    name = params.get("name")
                    args = params.get("arguments", {})
                    if not name:
                        raise ValueError("Missing tool name in params")
                    
                    res = await self.proxy.execute_tool(name, args)
                    result = res.model_dump() if hasattr(res, 'model_dump') else res
                else:
                    result = {"error": {"code": -32601, "message": f"Method {mcp_msg.method} not implemented"}}

                # 確保 result 是可序列化的
                response = {
                    "jsonrpc": "2.0",
                    "id": mcp_msg.id,
                    "result": result
                } if "error" not in str(result) else result
                
                import json
                await session_queues[sessionId].put(json.dumps(response))
                
                return {"status": "accepted"}

            except McpProxyError as e:
                import json
                error_resp = {
                    "jsonrpc": "2.0",
                    "id": mcp_msg.id,
                    "error": {"code": -32000, "message": str(e)}
                }
                await session_queues[sessionId].put(json.dumps(error_resp))
                return {"status": "error", "detail": str(e)}
            except Exception as e:
                logger.exception(f"處理訊息時發生未預期錯誤: {e}")
                import json
                error_resp = {
                    "jsonrpc": "2.0",
                    "id": mcp_msg.id,
                    "error": {"code": -32603, "message": "Internal error"}
                }
                await session_queues[sessionId].put(json.dumps(error_resp))
                return {"status": "error", "detail": "Internal server error"}

    async def start_proxy(self):
        """初始化底層 MCP 代理"""
        self.proxy = McpProxy()
        await self.proxy.__aenter__()
        logger.info("底層 MCP 代理已初始化並啟動")

    async def stop_proxy(self):
        """關閉底層 MCP 代理"""
        if self.proxy:
            await self.proxy.__aexit__(None, None, None)
            logger.info("底層 MCP 代理已關閉")
