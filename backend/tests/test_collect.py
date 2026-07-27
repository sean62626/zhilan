"""测试完整采集流程"""
import asyncio, sys, os
sys.path.insert(0, '/app')
os.chdir('/app')

async def main():
    from app.agents.collector import run_collection
    result = await run_collection()
    print(f"总数据源: {result.total_sources}")
    print(f"成功源: {result.successful_sources}")
    print(f"文章数: {len(result.articles)}")
    for k, v in result.source_stats.items():
        print(f"  [{k}] status={v.get('status')}, count={v.get('count')}, error={v.get('error')}")
    if result.articles:
        for a in result.articles[:3]:
            print(f"  📰 {a.title[:60]}... [{a.source}]")

asyncio.run(main())
