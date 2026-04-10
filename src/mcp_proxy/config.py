from pydantic_settings import BaseSettings

class McpSettings(BaseSettings):
    # 傳輸模式: "http" 或 "stdio"
    transport_type: str = "stdio"
    
    # HTTP 模式端點
    mcp_endpoint: str = "http://localhost:8080" 
    
    # Stdio 模式執行檔路徑
    mcp_exe_path: str = r"C:\tools\Orbination\Orbination-AI-Desktop-Vision-Control\DesktopControlMcp\bin\Release\net8.0-windows10.0.22621.0\DesktopControlMcp.exe"
    
    # 伺服器設定 (用於 Open WebUI 閘道)
    server_host: str = "0.0.0.0"
    server_port: int = 8082
    server_api_key: str = "mcp-proxy-secret-key" # 建議在生產環境中使用環境變數
    
    # 是否使用 Mock 模式 (當伺服器無法連線時可用於開發)
    use_mock: bool = False
    
    # 逾時設定 (秒)
    request_timeout: float = 30.0
    
    # 重試設定
    max_retries: int = 3
    retry_backoff_factor: float = 1.5
    
    # 安全標頭
    user_agent: str = "McpProxy/1.0.0 (Production)"
    
    class Config:
        env_prefix = "MCP_"
        case_sensitive = False

settings = McpSettings()
