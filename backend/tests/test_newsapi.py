"""快测 NewsAPI 是否还有配额"""
import asyncio, httpx

async def main():
    async with httpx.AsyncClient(timeout=15) as c:
        resp = await c.get('https://newsapi.org/v2/everything', params={
            'q': 'AI', 'language': 'zh', 'pageSize': 5, 'sortBy': 'publishedAt',
            'apiKey': '2e479b5f4cdb4c179083d5bb7abf5339'
        })
        print(f'HTTP {resp.status_code}')
        data = resp.json()
        print(f"status={data.get('status')}, total={data.get('totalResults')}, articles={len(data.get('articles',[]))}")
        if data.get('message'):
            print(f"message={data.get('message')}")
        if data.get('code'):
            print(f"code={data.get('code')}")

asyncio.run(main())
