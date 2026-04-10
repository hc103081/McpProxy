import pytest
from src.mcp_proxy.protocol import JsonRpcRequest, JsonRpcResponse, JsonRpcError

def test_json_rpc_request_creation():
    req = JsonRpcRequest(method="test_method", id=1, params={"a": 1})
    assert req.jsonrpc == "2.0"
    assert req.method == "test_method"
    assert req.id == 1
    assert req.params == {"a": 1}

def test_json_rpc_response_success():
    res = JsonRpcResponse(id=1, result={"status": "ok"})
    assert res.jsonrpc == "2.0"
    assert res.result == {"status": "ok"}
    assert res.error is None

def test_json_rpc_response_error():
    err = JsonRpcError(code=-32601, message="Method not found")
    res = JsonRpcResponse(id=1, error=err)
    assert res.error.code == -32601
    assert res.error.message == "Method not found"
