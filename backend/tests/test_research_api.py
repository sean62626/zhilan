"""直接测试 /pipeline/research 端点"""
import httpx
import asyncio
import json
from datetime import datetime, timezone
from app.models.article import CleanArticle, TopicCluster


async def main():
    # 构建小型测试数据
    articles = [
        CleanArticle(
            id="t1", title="美联储维持利率不变 暗示9月可能降息",
            url="https://example.com/1",
            cleaned_content="美联储在7月FOMC会议上决定维持联邦基金利率在5.25%-5.50%区间不变。"
            "主席鲍威尔在新闻发布会上表示，通胀正在朝着2%的目标回落，"
            "如果数据支持，9月会议可能讨论降息。市场对此反应积极，美股三大指数收涨。",
            source="rss", source_name="CNBC", language="zh",
        ),
        CleanArticle(
            id="t2", title="美国6月CPI同比降至3% 创两年新低",
            url="https://example.com/2",
            cleaned_content="美国劳工部公布数据显示，6月CPI同比上涨3.0%，低于预期的3.1%，"
            "为2021年3月以来最低水平。核心CPI同比上涨3.3%，也低于预期。"
            "数据公布后，美元指数下跌，黄金价格上涨。",
            source="rss", source_name="MarketWatch", language="zh",
        ),
        CleanArticle(
            id="t3", title="中国央行下调MLF利率10个基点",
            url="https://example.com/3",
            cleaned_content="中国人民银行开展中期借贷便利操作，中标利率下调10个基点至2.5%。"
            "分析师认为此举旨在降低实体经济融资成本，支持经济复苏。"
            "A股市场对此反应平淡，沪指小幅波动。",
            source="crawler", source_name="新浪财经", language="zh",
        ),
        CleanArticle(
            id="t4", title="全球央行政策分化 欧洲央行暗示继续加息",
            url="https://example.com/4",
            cleaned_content="欧洲央行行长拉加德表示，欧元区通胀仍然过高，"
            "可能需要继续加息以确保通胀回到2%目标。这与美联储的鸽派信号形成鲜明对比。"
            "欧元兑美元汇率升至1.12上方。",
            source="rss", source_name="Reuters", language="zh",
        ),
    ]

    clusters = [
        TopicCluster(
            cluster_id=0,
            label="全球央行货币政策动态",
            importance=10,
            articles=articles,
            article_count=4,
            representative_title=articles[0].title,
            keywords=["美联储", "利率", "央行", "货币政策"],
        ),
    ]

    # 发送到研究端点
    payload = {
        "clusters": [c.model_dump(mode="json") for c in clusters],
        "articles": [a.model_dump(mode="json") for a in articles],
        "max_reports": 2,
    }

    async with httpx.AsyncClient(timeout=180) as client:
        print("发送研究请求...")
        resp = await client.post(
            "http://localhost:8000/api/v1/pipeline/research",
            params={"max_reports": 2},
            json=payload,
        )
        print(f"HTTP {resp.status_code}")

        if resp.status_code == 200:
            data = resp.json()
            print(f"status: {data['status']}")
            for r in data.get("reports", []):
                print(f"\n--- 研报 ---")
                print(f"title: {r.get('title', '?')}")
                print(f"model: {r.get('model_used', '?')}")
                print(f"queries: {r.get('queries_used', [])}")
                print(f"retrieved: {r.get('docs_retrieved', 0)}")
                print(f"elapsed: {r.get('elapsed_seconds', 0)}s")
                for s in ['background', 'analysis', 'outlook', 'risk']:
                    text = r.get(s, '')
                    if text:
                        print(f"  {s}: {text[:120]}...")
        else:
            print(f"Error: {resp.text[:500]}")


if __name__ == "__main__":
    asyncio.run(main())
