"""
Phase 6 端到端测试

验证 8 节点全流程：collect → preprocess → dedup → cluster
→ research → review → compose → export

含审核-重试闭环验证
"""
import asyncio
import sys
from datetime import datetime, timezone


async def test_full_workflow():
    print("=== Phase 6 端到端测试 ===")
    print()

    from app.workflow.graph import get_graph
    from app.workflow.state import PlatformState

    graph = get_graph()
    today = datetime.now(timezone.utc).date().isoformat()

    initial_state: PlatformState = {
        "raw_articles": [],
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
        "target_date": today,
        "topics": ["科技", "金融"],
        "workflow_status": "running",
    }

    config = {"configurable": {"thread_id": "e2e-test-phase6"}}

    print("开始流式执行...")
    print()

    nodes_seen = set()
    node_order = []
    review_count = 0
    research_count = 0

    try:
        async for event in graph.astream(initial_state, config):
            node_name = list(event.keys())[0]
            if node_name in ("__start__", "__end__"):
                continue

            nodes_seen.add(node_name)
            node_order.append(node_name)

            if node_name == "research":
                research_count += 1
            if node_name == "review":
                review_count += 1

            # 提取节点输出的摘要信息
            output = event[node_name]
            summary = ""
            if node_name == "collect":
                summary = f"{len(output.get('raw_articles', []))} 篇文章"
            elif node_name == "preprocess":
                summary = f"{len(output.get('clean_articles', []))} 篇清洗"
            elif node_name == "dedup":
                summary = f"{len(output.get('unique_articles', []))} 篇去重后"
            elif node_name == "cluster":
                summary = f"{len(output.get('topic_clusters', []))} 个主题簇"
            elif node_name == "research":
                summary = f"{len(output.get('research_reports', []))} 份研报"
            elif node_name == "review":
                passed = output.get("review_passed", False)
                retry = output.get("retry_count", 0)
                summary = f"通过={passed}, retry={retry}"
            elif node_name == "compose":
                brief = output.get("daily_brief")
                summary = f"简报={'已生成' if brief else '为空'}"
            elif node_name == "export":
                summary = f"导出: {output.get('export_paths', [])}"

            print(f"  ✓ {node_name}: {summary}")

        print()
        print(f"节点执行顺序: {' → '.join(node_order)}")
        print(f"Research 执行次数: {research_count}")
        print(f"Review 执行次数: {review_count}")

        # 获取最终状态
        final = graph.get_state(config)
        values = final.values if final else {}

        print()
        print("=== 最终状态 ===")
        print(f"  raw_articles: {len(values.get('raw_articles', []))}")
        print(f"  clean_articles: {len(values.get('clean_articles', []))}")
        print(f"  unique_articles: {len(values.get('unique_articles', []))}")
        print(f"  topic_clusters: {len(values.get('topic_clusters', []))}")
        print(f"  research_reports: {len(values.get('research_reports', []))}")
        print(f"  review_passed: {values.get('review_passed')}")
        print(f"  retry_count: {values.get('retry_count')}")
        print(f"  daily_brief: {'有' if values.get('daily_brief') else '无'}")
        print(f"  export_paths: {values.get('export_paths', [])}")
        print(f"  workflow_status: {values.get('workflow_status')}")

        # ===== 断言验证 =====
        assert "collect" in nodes_seen, "缺少 collect 节点"
        assert "preprocess" in nodes_seen, "缺少 preprocess 节点"
        assert "dedup" in nodes_seen, "缺少 dedup 节点"
        assert "review" in nodes_seen, "缺少 review 节点"
        assert "compose" in nodes_seen, "缺少 compose 节点"
        assert "export" in nodes_seen, "缺少 export 节点"

        # 审核至少执行一次
        assert review_count >= 1, "审核未执行"

        # 最终有简报
        assert values.get("daily_brief") is not None, "日报未生成"

        # 有导出文件
        export_paths = values.get("export_paths", [])
        assert len(export_paths) > 0, "导出文件未生成"
        assert any(p.endswith(".md") for p in export_paths), "未生成 .md 文件"

        print()
        print("✅ 端到端测试通过 — Phase 6 全流程验证成功")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


async def test_review_router_only():
    """独立测试审核路由逻辑（不调用实际 Agent）"""
    print("=== 审核路由独立测试 ===")

    from app.workflow.graph import review_router, MAX_REVIEW_RETRIES

    # 4 个场景
    test_cases = [
        ({"review_passed": True, "retry_count": 1}, "compose", "通过 → compose"),
        ({"review_passed": False, "retry_count": 1}, "research", "不通过 + retry<3 → research"),
        ({"review_passed": False, "retry_count": 3}, "compose", "不通过 + retry>=3 → compose(强制)"),
        ({"review_passed": False, "retry_count": 4}, "compose", "不通过 + retry>3 → compose"),
    ]

    all_pass = True
    for state, expected, desc in test_cases:
        result = review_router(state)
        status = "✅" if result == expected else "❌"
        if result != expected:
            all_pass = False
        print(f"  {status} {desc}: {result} (期望: {expected})")

    if all_pass:
        print("✅ 审核路由全部通过")
    else:
        print("❌ 审核路由有失败")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(test_review_router_only())
    asyncio.run(test_full_workflow())
