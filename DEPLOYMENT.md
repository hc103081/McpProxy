# MCP HTTP 遷移部署指南

## 1. 概述
本文件說明將 MCP 服務從本地 COM 註冊遷移至 HTTP MCP 實作 (`https://hc103081.servehttp.com/`) 的部署流程。

## 2. 環境要求
- **Python**: >= 3.12
- **依賴庫**:
  - `httpx`: 異步 HTTP 客戶端
  - `pydantic`: 資料驗證與設定管理
  - `pydantic-settings`: 環境變數管理
  - `tenacity`: 請求重試機制
  - `pytest`, `pytest-asyncio`, `respx`: 測試框架

## 3. 安裝與配置

### 依賴安裝
```bash
pip install httpx pydantic pydantic-settings tenacity
```

### 環境變數設定
您可以使用環境變數來覆蓋 `src/mcp_proxy/config.py` 中的預設值：
- `MCP_MCP_ENDPOINT`: 伺服器端點 (預設: `https://hc103081.servehttp.com/`)
- `MCP_REQUEST_TIMEOUT`: 請求逾時秒數 (預設: `30.0`)
- `MCP_MAX_RETRIES`: 最大重試次數 (預設: `3`)

## 4. 升級指引 (Migration Path)

### 步驟 1: 部署新版本
將 `src/` 目錄部署至生產環境。

### 步驟 2: 驗證連通性
執行 `main.py` 並選擇 `n` (不執行本地註冊)，確認能成功連線至 HTTP 端點並獲取工具列表。

### 步驟 3: 切換流量
將既有服務的調用方指向 `McpProxy` 的新介面。由於我們保持了相同的介面簽名，調用方無需修改代碼。

### 步驟 4: 回滾 (Rollback)
若發現異常，請將 `main.py` 恢復至舊版本，並重新執行本地 COM 註冊流程。

## 5. 連通性驗證方法
可以使用以下簡單腳本驗證端點是否可用：
```python
import httpx
import asyncio

async def check():
    async with httpx.AsyncClient() as client:
        resp = await client.post("https://hc103081.servehttp.com/", 
                                 json={"jsonrpc": "2.0", "method": "initialize", "params": {}, "id": 1})
        print(f"Status: {resp.status_code}, Body: {resp.text}")

asyncio.run(check())
```

## 6. 生產等級保障
- **安全標頭**: 客戶端已強制加入 `X-Content-Type-Options`, `X-Frame-Options` 及 `HSTS` 標頭。
- **穩定性**: 實作了指數退避 (Exponential Backoff) 重試機制。
- **驗證**: 所有請求與回應均通過 Pydantic 模型強制驗證。
