# Open WebUI $\rightarrow$ McpProxy $\rightarrow$ 本地 MCP 服務部署指南

本指南說明如何將 Open WebUI 連接至本地端 MCP 服務，透過 `McpProxy` 作為 HTTP/SSE 閘道，實現遠端調用本地桌面控制工具。

## 🛠️ 系統架構
`Open WebUI` $\xrightarrow{\text{HTTP/SSE}}$ `servehttp.com (隧道)` $\xrightarrow{\text{HTTP}}$ `McpProxy (FastAPI Server)` $\xrightarrow{\text{Stdio}}$ `DesktopControlMcp.exe`

---

## 🚀 部署步驟

### 1. 啟動 McpProxy 閘道伺服器
在本地端開啟終端機，進入 `McpProxy` 專案目錄，執行以下指令啟動伺服器：

```powershell
uv run main.py server
```
**確認輸出：**
- 看到 `Uvicorn running on http://0.0.0.0:8082` 表示伺服器已成功啟動。
- 看到 `底層 MCP 代理已初始化並啟動` 表示已成功連接到 `DesktopControlMcp.exe`。

### 2. 配置公網隧道 (servehttp.com)
由於 Open WebUI 通常位於雲端或不同網路，您需要將本地的 `8082` 埠口映射到公網。

- **工具**：使用 `servehttp.com` 或 `ngrok` 等隧道工具。
- **配置**：將本地 `http://localhost:8082` 映射至 `https://hc103081.servehttp.com`。
- **驗證**：在瀏覽器訪問 `https://hc103081.servehttp.com/docs`，若能看到 Swagger UI 界面，則隧道配置成功。

### 3. Open WebUI 設定
1. 登入 **Open WebUI**。
2. 進入 **設定 (Settings)** $\rightarrow$ **外部連接 (Connections)** $\rightarrow$ **MCP 伺服器 (MCP Servers)**。
3. 點擊 **添加伺服器 (Add Server)**：
   - **名稱 (Name)**：`Desktop Control` (可自定義)
   - **類型 (Type)**：選擇 `SSE`
   - **URL**：`https://hc103081.servehttp.com/sse`
4. 點擊 **儲存 (Save)**。

---

## ✅ 驗證與測試

### 1. 確認工具載入
在 Open WebUI 的對話框中，輸入 `/` 或查看工具圖標，確認是否出現了 `get_screen_info`, `mouse_click` 等 47 個工具。

### 2. 執行測試指令
嘗試向 AI 發送指令：
> 「請幫我獲取目前的螢幕資訊」

**預期結果：**
AI 會調用 `get_screen_info` 工具 $\rightarrow$ `McpProxy` 轉發至 `DesktopControlMcp.exe` $\rightarrow$ 回傳螢幕解析度 $\rightarrow$ AI 回答您。

---

## 🔍 錯誤排查與日誌檢查

### 1. 常見錯誤碼
| 錯誤現象 | 可能原因 | 解決方案 |
| :--- | :--- | :--- |
| **Connection Failed / 404** | 隧道中斷或埠口錯誤 | 檢查 `uv run main.py server` 是否在運行，並確認隧道映射的是 `8082` 埠口 |
| **405 Method Not Allowed** | 請求路徑錯誤 | 確認 Open WebUI 設定的 URL 以 `/sse` 結尾 |
| **JSON-RPC Error -32601** | 工具名稱不匹配 | 檢查伺服器日誌，確認工具名稱是否正確 |
| **Timeout** | 本地服務無回應 | 檢查 `DesktopControlMcp.exe` 是否被防火牆攔截或崩潰 |

### 2. 日誌檢查路徑
- **伺服器日誌**：直接查看執行 `uv run main.py server` 的終端機視窗。
- **詳細模式**：若需更詳細的除錯資訊，可使用 `uv run main.py --verbose server`。
- **Stdio 錯誤**：若看到 `解析 Stdio JSON-RPC 回應失敗`，通常是伺服器輸出了非 JSON 的日誌，`McpProxy` 已內建過濾機制，若持續發生請檢查伺服器版本。

---

## 🔐 安全建議
目前伺服器對外開放。若要增加安全性，建議：
1. **API Key 驗證**：在 `config.py` 中設定 `server_api_key`，並在 `server.py` 的 `messages_endpoint` 中增加 Header 檢查。
2. **防火牆限制**：僅允許 Open WebUI 的伺服器 IP 訪問您的隧道埠口。
