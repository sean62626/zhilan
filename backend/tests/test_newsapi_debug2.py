"""调试 NewsAPI — 对比中英文查询"""
import asyncio, httpx
from datetime import datetime, timedelta, timezone

API_KEY = "2e479b5f4cdb4c179083d5bb7abf5339"
BASE = "https://newsapi.org/v2"

async def test_query(q, lang, label):
    async with httpx.AsyncClient(timeout=15.0) as c:
        try:
            params = {
                "q": q, "language": lang, "pageSize": 3,
                "sortBy": "publishedAt", "apiKey": API_KEY,
                "from": (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S"),
            }
            # 手动 URL 编码中文参数
            resp = await c.get(f"{BASE}/everything", params=params)
            data = resp.json()
            print(f"[OK]  {label}: HTTP {resp.status_code}, total={data.get('totalResults')}, articles={len(data.get('articles',[]))}")
        except Exception as e:
            print(f"[FAIL] {label}: {type(e).__name__}: {e}")

async def main():
    print("=== NewsAPI 参数对比测试 ===\n")
    await test_query("AI", "zh", "q=AI, lang=zh")
    await test_query("finance", "zh", "q=finance, lang=zh")
    await test_query("财经", "zh", "q=财经, lang=zh")
    await test_query("科技", "zh", "q=科技, lang=zh")
    await test_query("AI", "en", "q=AI, lang=en")
    await test_query("finance", "en", "q=finance, lang=en")

asyncio.run(main())
