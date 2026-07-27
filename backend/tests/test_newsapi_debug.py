"""调试 NewsAPI 采集器为什么返回 0"""
import asyncio, httpx
from datetime import datetime, timedelta, timezone

async def main():
    api_key = "2e479b5f4cdb4c179083d5bb7abf5339"
    base_url = "https://newsapi.org/v2"
    languages = ["zh", "en"]
    topics = ["财经", "科技", "宏观经济"]
    page_size = 50

    async with httpx.AsyncClient(timeout=30.0) as client:
        for lang in languages:
            for topic in topics:
                params = {
                    "q": topic,
                    "language": lang,
                    "pageSize": min(page_size, 100),
                    "sortBy": "publishedAt",
                    "apiKey": api_key,
                    "from": (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S"),
                }
                print(f"\n查询: q={topic}, lang={lang}")
                resp = await client.get(f"{base_url}/everything", params=params)
                print(f"  HTTP {resp.status_code}")
                data = resp.json()
                print(f"  status={data.get('status')}, total={data.get('totalResults')}, articles={len(data.get('articles',[]))}")
                if data.get('message'):
                    print(f"  message={data.get('message')}")
                if data.get('articles'):
                    for a in data['articles'][:2]:
                        print(f"    - {a.get('title','?')[:80]}")

asyncio.run(main())
