import pytest
import respx
import httpx
from src.mcp_proxy.client import McpHttpClient
from src.mcp_proxy.exceptions import McpHttpError, McpRemoteError
from src.mcp_proxy.config import settings

@pytest.mark.asyncio
async def test_initialize_success():
    async with McpHttpClient() as client:
        with respx.mock:
            # Mock the initialize response
            respx.post(settings.mcp_endpoint).mock(return_value=httpx.Response(
                200, 
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "serverInfo": {"name": "TestServer", "version": "1.0.0"}
                    }
                }
            ))
            
            result = await client.initialize()
            assert result.protocolVersion == "2024-11-05"
            assert result.serverInfo["name"] == "TestServer"

@pytest.mark.asyncio
async def test_initialize_remote_error():
    async with McpHttpClient() as client:
        with respx.mock:
            respx.post(settings.mcp_endpoint).mock(return_value=httpx.Response(
                200, 
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "error": {
                        "code": -32600,
                        "message": "Invalid Request"
                    }
                }
            ))
            
            with pytest.raises(McpRemoteError) as excinfo:
                await client.initialize()
            assert excinfo.value.code == -32600
            assert "Invalid Request" in excinfo.value.message

@pytest.mark.asyncio
async def test_http_error():
    async with McpHttpClient() as client:
        with respx.mock:
            respx.post(settings.mcp_endpoint).mock(return_value=httpx.Response(500))
            
            with pytest.raises(McpHttpError) as excinfo:
                await client._send_request("test", request_id=1)
            assert excinfo.value.status_code == 500
