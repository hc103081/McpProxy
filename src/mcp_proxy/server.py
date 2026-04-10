import asyncio
import logging
import uuid
import os
from typing import Any, Dict, Optional
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

from .proxy import McpProxy
from .config import settings
from .exceptions import McpProxyError
from .todo import TodoManager, TodoItem
from .utils import get_resource_path

logger = logging.getLogger(__name__)

# 儲存每個 session 的訊息隊列，用於將結果推送到 SSE 流
session_queues: Dict[str, asyncio.Queue] = {}

class McpMessage(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Optional[Any] = None

class TodoCreate(BaseModel):
    content: str
    priority: str = "medium"

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
        self.todo_manager = TodoManager()
        self._setup_routes()

    async def _handle_mcp_message(self, request: Request, sessionId: Optional[str] = None):
        """
        核心指令處理邏輯：
        1. 解析請求體，判斷是否為 MCP JSON-RPC 格式。
        2. 如果是 MCP 指令 $\rightarrow$ 處理並根據 sessionId 決定回傳方式 (SSE 隊列 或 直接 HTTP 回傳)。
        3. 如果不是 MCP 指令 $\rightarrow$ 回傳基礎健康檢查狀態。
        """
        try:
            body = await request.json()
        except Exception:
            return {"status": "ok", "message": "Endpoint active (non-JSON request)"}

        # 檢查是否符合 MCP JSON-RPC 規範
        is_mcp_request = isinstance(body, dict) and "jsonrpc" in body and "method" in body
        
        if not is_mcp_request:
            return {"status": "ok", "message": "SSE endpoint is active"}

        # 處理 MCP 指令
        try:
            mcp_msg = McpMessage(**body)
            result = None
            if mcp_msg.method == "initialize":
                res = await self.proxy.client.initialize()
                result = res.model_dump() if hasattr(res, 'model_dump') else res
            elif mcp_msg.method == "tools/list":
                res = await self.proxy.get_available_tools()
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

            response = {
                "jsonrpc": "2.0",
                "id": mcp_msg.id,
                "result": result
            } if "error" not in str(result) else result

            # --- 關鍵邏輯：決定回傳路徑 ---
            if sessionId and sessionId in session_queues:
                # 有有效 Session $\rightarrow$ 走 SSE 隊列 (標準流程)
                import json
                await session_queues[sessionId].put(json.dumps(response))
                return {"status": "accepted"}
            else:
                # 無 Session $\rightarrow$ 直接回傳結果 (滿足 Open WebUI 初始握手)
                logger.info(f"無 SessionId，直接回傳 MCP 結果給客戶端 (Method: {mcp_msg.method})")
                return response

        except McpProxyError as e:
            error_resp = {"jsonrpc": "2.0", "id": getattr(body, 'get', lambda x: None)('id'), "error": {"code": -32000, "message": str(e)}}
            if sessionId and sessionId in session_queues:
                import json
                await session_queues[sessionId].put(json.dumps(error_resp))
                return {"status": "error", "detail": str(e)}
            return error_resp
        except Exception as e:
            logger.exception(f"處理 MCP 訊息時發生錯誤: {e}")
            error_resp = {"jsonrpc": "2.0", "id": getattr(body, 'get', lambda x: None)('id'), "error": {"code": -32603, "message": "Internal error"}}
            if sessionId and sessionId in session_queues:
                import json
                await session_queues[sessionId].put(json.dumps(error_resp))
                return {"status": "error", "detail": "Internal server error"}
            return error_resp

    def _setup_routes(self):
        # 靜態文件掛載
        static_dir = get_resource_path("static")
        self.app.mount("/static", StaticFiles(directory=static_dir), name="static")

        @self.app.get("/")
        async def index():
            """回傳管理控制台主頁"""
            return FileResponse(get_resource_path("static/index.html"))

        # --- Todo 管理 API ---
        @self.app.get("/api/todos")
        async def get_todos():
            """獲取所有待辦事項"""
            return self.todo_manager.get_all_todos()

        @self.app.post("/api/todos")
        async def create_todo(todo: TodoCreate):
            """創建新的待辦事項"""
            return self.todo_manager.add_todo(content=todo.content, priority=todo.priority)

        @self.app.put("/api/todos/{todo_id}")
        async def update_todo(todo_id: str, updates: Dict[str, Any]):
            """更新待辦事項"""
            res = self.todo_manager.update_todo(todo_id, updates)
            if not res:
                raise HTTPException(status_code=404, detail="Todo not found")
            return res

        @self.app.delete("/api/todos/{todo_id}")
        async def delete_todo(todo_id: str):
            """刪除待辦事項"""
            if not self.todo_manager.delete_todo(todo_id):
                raise HTTPException(status_code=404, detail="Todo not found")
            return {"status": "success", "message": "Todo deleted"}

        @self.app.patch("/api/todos/{todo_id}/toggle")
        async def toggle_todo(todo_id: str):
            """切換完成狀態"""
            res = self.todo_manager.toggle_todo(todo_id)
            if not res:
                raise HTTPException(status_code=404, detail="Todo not found")
            return res

        # --- 日誌監控 API ---
        @self.app.get("/api/logs")
        async def get_logs():
            """獲取最近的系統日誌"""
            log_path = "system.log"
            if not os.path.exists(log_path):
                return {"logs": [], "message": "Log file not found"}
            
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    return {"logs": lines[-100:]} # 回傳最後 100 行
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Read log failed: {e}")

        @self.app.get("/api/logs/stream")
        async def stream_logs():
            """實時流式傳輸日誌 (SSE)"""
            async def event_generator():
                log_path = "system.log"
                if not os.path.exists(log_path):
                    yield {"event": "error", "data": "Log file not found"}
                    return

                # 先讀取最後一部分
                with open(log_path, "r", encoding="utf-8") as f:
                    f.seek(0, os.SEEK_END)
                    file_size = f.tell()
                    # 讀取最後 10KB
                    offset = max(0, file_size - 10240)
                    f.seek(offset)
                    for line in f:
                        yield {"event": "log", "data": line.strip()}

                # 開始追蹤新行
                with open(log_path, "r", encoding="utf-8") as f:
                    f.seek(0, os.SEEK_END)
                    while True:
                        line = f.readline()
                        if not line:
                            await asyncio.sleep(0.5)
                            continue
                        yield {"event": "log", "data": line.strip()}

            return EventSourceResponse(event_generator())

        @self.app.api_route("/sse", methods=["GET", "POST"])
        async def sse_endpoint(request: Request):
            """
            建立 SSE 連線，並告知客戶端發送訊息的端點。
            同時支持 POST 請求以兼容某些客戶端的連線檢查或指令發送。
            """
            if request.method == "POST":
                # 無論是否有 sessionId，都交由 _handle_mcp_message 判斷
                # 如果是 MCP 指令則處理，如果只是健康檢查則回傳 ok
                session_id = request.query_params.get("sessionId")
                return await self._handle_mcp_message(request, session_id)

            session_id = str(uuid.uuid4())
            queue = asyncio.Queue()
            session_queues[session_id] = queue
            
            logger.info(f"新 SSE 連線建立: {session_id}")

            async def event_generator():
                try:
                    yield {
                        "event": "endpoint",
                        "data": f"/messages?sessionId={session_id}"
                    }
                    
                    while True:
                        if await request.is_disconnected():
                            break
                        
                        try:
                            data = await asyncio.wait_for(queue.get(), timeout=15.0)
                            yield {
                                "event": "message",
                                "data": data
                            }
                        except asyncio.TimeoutError:
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
                    "X-Accel-Buffering": "no",
                }
            )

        @self.app.post("/messages")
        async def messages_endpoint(request: Request, sessionId: str):
            """
            接收客戶端的 JSON-RPC 請求並轉發給 MCP 伺服器。
            """
            if sessionId not in session_queues:
                raise HTTPException(status_code=404, detail="Session not found")

            return await self._handle_mcp_message(request, sessionId)

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
