"""
冒烟测试 — 跳过采集，用模拟文章运行完整 8 节点工作流

直接调用各节点函数，避免 graph 从 START→collect 覆盖模拟数据。
"""
import asyncio
import time
from datetime import datetime, timezone

from app.models.article import RawArticle, CleanArticle
from app.workflow.nodes import (
    preprocess_node,
    dedup_node,
    cluster_node,
    research_node,
    review_node,
    compose_node,
    export_node,
)


async def main():
    # ====== 构造15篇模拟文章 ======
    titles = [
        "OpenAI 发布 GPT-5，推理能力大幅提升",
        "中国 AI 产业规模突破万亿大关",
        "美联储维持利率不变，市场反应积极",
        "特斯拉 FSD 在华获批，股价大涨",
        "央行数字货币跨境支付试点扩围",
        "全球芯片供应链正在重塑格局",
        "新能源车销量同比增长 45%",
        "欧盟通过人工智能法案最终版本",
        "量子计算商用化取得关键突破",
        "Meta 发布开源大模型 Llama 4",
        "华为发布鸿蒙 5.0 全场景操作系统",
        "比特币突破 15 万美元创历史新高",
        "脑机接口首次实现人类临床试验",
        "东南亚数字经济增速领跑全球",
        "SpaceX 星舰成功完成载人登月任务",
    ]
    raw_articles = []
    for i, title in enumerate(titles):
        article = {
            "id": f"mock-{i:04d}",
            "title": title,
            "url": f"https://example.com/news/{i}",
            "content": f"{title}。这是关于该事件的详细报道内容，涵盖了主要背景、关键数据和各方反应。"
            * 10,
            "source": "newsapi",
            "source_name": "MockSource",
            "language": "zh",
            "published_at": datetime.now(timezone.utc).isoformat(),
        }
        raw_articles.append(article)

    # 初始 state（模拟 collect 已完成）
    state: dict = {
        "raw_articles": raw_articles,
        "collection_errors": [],
        "clean_articles": [],
        "unique_articles": [],
        "dedup_stats": {},
        "topic_clusters": [],
        "research_reports": [],
        "review_results": [],
        "review_passed": False,
        "retry_count": 0,
        "daily_brief": None,
        "export_paths": [],
        "errors": [],
        "target_date": datetime.now(timezone.utc).date().isoformat(),
        "topics": ["AI", "科技", "金融"],
        "workflow_status": "running",
    }

    print("=== 8 节点工作流冒烟测试 ===")
    print(f"模拟文章: {len(raw_articles)} 篇")
    print()

    steps = [
        ("preprocess", preprocess_node),
        ("dedup", dedup_node),
        ("cluster", cluster_node),
        ("research", research_node),
        ("review", review_node),
        ("compose", compose_node),
        ("export", export_node),
    ]

    for name, node_fn in steps:
        print(f"  ⏳ {name}...", end=" ", flush=True)
        try:
            result = await node_fn(state)
            state.update(result)
            print("✅")
        except Exception as e:
            print(f"❌ {e}")
            state["errors"] = state.get("errors", []) + [f"{name}: {e}"]

    print()
    print("=== 结果 ===")
    print(f"  去重后文章: {len(state.get('unique_articles', []))} 篇")
    print(f"  主题簇:     {len(state.get('topic_clusters', []))} 个")
    for c in state.get("topic_clusters", [])[:5]:
        print(f"    - {c.get('label', '?')} (重要度: {c.get('importance', '?')})")
    print(f"  研报:       {len(state.get('research_reports', []))} 份")
    print(f"  审核通过:   {state.get('review_passed', False)}")
    print(f"  日报:       {'✅ 已生成' if state.get('daily_brief') else '❌ 无'}")
    print(f"  导出文件:   {state.get('export_paths', [])}")
    errs = state.get("errors", [])
    if errs:
        print(f"  错误:       {errs[:5]}")


if __name__ == "__main__":
    asyncio.run(main())
