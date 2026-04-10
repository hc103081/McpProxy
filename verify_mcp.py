import asyncio
import httpx
import time
import sys

ENDPOINT = "https://hc103081.servehttp.com/"

async def verify():
    print(f"開始驗收測試: 連接至 {ENDPOINT}")
    start_time = time.time()
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 模擬 MCP initialize 請求
            payload = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "Verifier", "version": "1.0"}
                },
                "id": 1
            }
            
            print("發送 initialize 請求...")
            resp = await client.post(ENDPOINT, json=payload)
            
            if resp.status_code != 200:
                print(f"❌ 驗收失敗: HTTP 狀態碼 {resp.status_code}")
                return False
            
            print("初始化成功，嘗試獲取工具列表 (tools/list)...")
            
            payload_list = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "params": {},
                "id": 2
            }
            
            resp_list = await client.post(ENDPOINT, json=payload_list)
            
            if resp_list.status_code != 200:
                print(f"❌ 驗收失敗: tools/list HTTP 狀態碼 {resp_list.status_code}")
                return False
            
            data = resp_list.json()
            tools = data.get("result", {}).get("tools", [])
            
            elapsed = time.time() - start_time
            if elapsed > 10.0:
                print(f"❌ 驗收失敗: 響應時間過長 ({elapsed:.2f}s > 10s)")
                return False
            
            print(f"✅ 驗收通過: {elapsed:.2f} 秒內回傳 {len(tools)} 項工具 (HTTP 200)")
            return True
            
    except Exception as e:
        print(f"❌ 驗收過程中發生異常: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(verify())
    sys.exit(0 if success else 1)
