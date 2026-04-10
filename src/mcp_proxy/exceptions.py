class McpProxyError(Exception):
    """McpProxy 基礎異常類別"""
    pass

class McpHttpError(McpProxyError):
    """HTTP 通訊異常 (例如 4xx, 5xx)"""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"HTTP Error {status_code}: {message}")

class McpProtocolError(McpProxyError):
    """MCP 協定層異常 (例如 JSON-RPC 格式錯誤)"""
    pass

class McpRemoteError(McpProxyError):
    """遠端伺服器回傳的 JSON-RPC 錯誤"""
    def __init__(self, code: int, message: str, data: any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"Remote MCP Error [{code}]: {message}")

class McpTimeoutError(McpProxyError):
    """請求逾時異常"""
    pass
