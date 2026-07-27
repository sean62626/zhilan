"""验证 NewsAPI from 参数问题"""
import asyncio, httpx
from datetime import datetime, timedelta, timezone

API_KEY = "2e479b5f4cdb4c179083d5bb7abf5339"
BASE = "https://newsapi.org/v2"

async def test(params, label):
    async with httpx.AsyncClient(timeout=15.0) as c:
        try:
            resp = await c.get(f"{BASE}/everything", params=params)
            data = resp.json()
            print(f"[OK]  {label}: total={data.get('totalResults')}, articles={len(data.get('articles',[]))}")
            if data.get('articles'):
                for a in data['articles'][:2]:
                    print(f"      {a.get('publishedAt','?')} | {a.get('title','?')[:70]}")
        except Exception as e:
            print(f"[FAIL] {label}: {e}")

async def main():
    print("=== from 参数影响测试 ===\n")

    base = {"q": "AI", "language": "zh", "pageSize": 3, "sortBy": "publishedAt", "apiKey": API_KEY}

    # 无 from
    await test(base, "无 from")

    # from=24h
    p24 = base.copy()
    p24["from"] = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")
    await test(p24, "from=24h前")

    # from=48h
    p48 = base.copy()
    p48["from"] = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%S")
    await test(p48, "from=48h前")

    # from=72h
    p72 = base.copy()
    p72["from"] = (datetime.now(timezone.utc) - timedelta(hours=72)).strftime("%Y-%m-%dT%H:%M:%S")
    await test(p72, "from=72h前")

asyncio.run(main())
