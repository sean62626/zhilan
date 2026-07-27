"""Phase 4 功能冒烟测试"""
import asyncio
from app.models.article import CleanArticle, TopicCluster, ResearchReport
from app.rag.context import estimate_tokens, assemble_context, format_references
from app.generators.report_writer import generate_report


async def smoke_test():
    # 1. Token 估算
    cn_tokens = estimate_tokens("这是一段中文测试文本用于验证token估算功能是否正常")
    en_tokens = estimate_tokens("This is an English test sentence for token estimation.")
    print(f"[OK] Token估算: 中文~{cn_tokens}t, 英文~{en_tokens}t")

    # 2. 构建假数据
    articles = [
        CleanArticle(
            id="test_1",
            title="美联储宣布维持利率不变",
            url="https://example.com/1",
            cleaned_content="美联储在7月会议上宣布维持联邦基金利率在5.25%-5.50%区间不变，符合市场预期。主席鲍威尔表示通胀正在回落但尚未达到目标。",
            source="rss", source_name="CNBC", language="zh",
        ),
        CleanArticle(
            id="test_2",
            title="A股三大指数集体收涨",
            url="https://example.com/2",
            cleaned_content="今日A股三大指数集体收涨，沪指涨0.8%报3250点，深成指涨1.2%，创业板指涨1.5%。北向资金净流入超50亿元。",
            source="rss", source_name="新浪财经", language="zh",
        ),
    ]

    # 3. 上下文组装
    docs = [(a, 0.9) for a in articles]
    ctx = assemble_context(docs, max_tokens=1000)
    print(f"[OK] 上下文组装: {len(ctx)} 字符")

    # 4. 引用格式化
    refs = format_references(docs)
    print(f"[OK] 引用格式化: {len(refs)} 条")

    # 5. 回退研报 (无 LLM)
    report = await generate_report(
        cluster_label="美联储利率决议",
        keywords=["美联储", "利率", "A股"],
        context_text=ctx,
        references=refs,
    )
    print(f"[OK] 回退研报: {report['title'][:50]}...")
    print(f"    model_used: {report['model_used']}")

    # 6. ResearchReport 模型
    r = ResearchReport(
        report_id="test_r1",
        cluster_id=0,
        title="测试研报",
        background="测试背景",
        analysis="测试分析",
        outlook="测试展望",
        risk="测试风险",
        references=refs,
        model_used="test",
    )
    print(f"[OK] ResearchReport 模型: id={r.report_id}, sections=4")

    # 7. 检索器测试
    from app.rag.retriever import hybrid_search
    results = await hybrid_search("美联储 利率", articles, top_k_knn=5, top_k_bm25=5)
    print(f"[OK] 混合检索: 召回 {len(results)} 篇")

    # 8. Reranker 测试
    from app.rag.reranker import rerank
    reranked = await rerank("美联储 利率", results, top_k=5)
    print(f"[OK] Rerank: {len(reranked)} 篇")

    print()
    print("=== Phase 4 功能验证全部通过 ===")


if __name__ == "__main__":
    asyncio.run(smoke_test())
