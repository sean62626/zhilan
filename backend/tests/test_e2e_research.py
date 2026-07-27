"""端到端测试: 完整管道含研报生成"""
import httpx
import asyncio
import json


async def main():
    async with httpx.AsyncClient(timeout=120) as client:
        # 先运行管道获取聚类数据和文章
        print("=== 阶段 1: 采集+预处理+去重+聚类 ===")
        resp = await client.post(
            "http://localhost:8000/api/v1/pipeline/run",
            params={"skip_research": True},
        )
        data = resp.json()
        print(f"status={data['status']}, clusters={data['clusters']['count']}, "
              f"dedup={data['dedup']['input']}->{data['dedup']['output']}")

        # 通过 /pipeline/cluster 端点获取完整 cluster 数据需要先有 articles
        # 所以我们直接用 /pipeline/research 端点加上从 /run 得到的基本信息
        # 但是 /pipeline/research 需要 TopicCluster 和 CleanArticle 对象
        # 最简单的方式: 直接调用 /pipeline/run?skip_research=false

        print()
        print("=== 阶段 2: 完整管道 (含研报生成) ===")
        resp2 = await client.post(
            "http://localhost:8000/api/v1/pipeline/run",
            params={"skip_research": False},
        )
        data2 = resp2.json()
        print(f"status={data2['status']}")
        print(f"clusters={data2['clusters']['count']}")
        print(f"reports={len(data2.get('reports', []))}")

        for r in data2.get("reports", []):
            print(f"\n--- 研报: {r.get('title', '?')} ---")
            print(f"    model: {r.get('model_used', '?')}")
            print(f"    queries: {r.get('queries_used', [])}")
            print(f"    retrieved: {r.get('docs_retrieved', 0)}, reranked: {r.get('docs_reranked', 0)}")
            print(f"    elapsed: {r.get('elapsed_seconds', 0)}s")
            if r.get('error'):
                print(f"    error: {r['error']}")
            # Print first 200 chars of each section
            for section in ['background', 'analysis', 'outlook', 'risk']:
                text = r.get(section, '')
                if text:
                    print(f"    {section}: {text[:100]}...")


if __name__ == "__main__":
    asyncio.run(main())
