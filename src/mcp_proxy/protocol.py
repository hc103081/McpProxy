from typing import Any, Optional, Union, Dict, List
from pydantic import BaseModel, Field

class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Union[int, str]

class JsonRpcError(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None

class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[JsonRpcError] = None
    id: Union[int, str]

# MCP Specific Models
class MCPInitializeRequest(BaseModel):
    protocolVersion: str = "2024-11-05"
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    clientInfo: Dict[str, str] = Field(default_factory=lambda: {"name": "McpProxy-Client", "version": "1.0.0"})

class MCPInitializeResult(BaseModel):
    protocolVersion: str
    capabilities: Dict[str, Any]
    serverInfo: Dict[str, str]

class MCPTool(BaseModel):
    name: str
    description: Optional[str] = None
    inputSchema: Dict[str, Any]

class MCPToolListResult(BaseModel):
    tools: List[MCPTool]

class MCPCallToolRequest(BaseModel):
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)

class MCPCallToolResult(BaseModel):
    content: List[Dict[str, Any]]
    isError: bool = False
