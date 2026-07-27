"""
模拟数据采集器 — 开发/测试专用

当真实数据源不可用时（API 配额耗尽、爬虫被拦截等），
提供模拟新闻数据供管道其他阶段开发调试。

启用方式：在 sources.yaml 中设置 mock.enabled: true
"""

import logging
from datetime import datetime, timezone, timedelta

from app.config import get_settings
from app.models.article import RawArticle

logger = logging.getLogger(__name__)

# 模拟新闻数据 — 涵盖科技、金融、国际三大主题
_MOCK_ARTICLES: list[dict] = [
    {
        "title": "OpenAI 发布 GPT-5：多模态推理能力大幅提升",
        "url": "https://example.com/news/openai-gpt5",
        "content": (
            "OpenAI 今日正式发布 GPT-5 模型，在数学推理、代码生成和多模态理解方面"
            "取得了显著突破。新模型在 MMLU 基准测试中达到 95.2% 的准确率，较 GPT-4 "
            "提升了 8.5 个百分点。CEO Sam Altman 表示，GPT-5 将首先通过 API 向企业"
            "客户开放，消费者版本将在下月推出。业界分析认为，这将对 Google Gemini "
            "和 Anthropic Claude 形成强力竞争。"
        ),
        "source_name": "科技日报",
        "language": "zh",
        "tags": ["AI", "大模型", "OpenAI"],
    },
    {
        "title": "央行宣布降准 0.5 个百分点，释放长期流动性约 1 万亿",
        "url": "https://example.com/news/pboc-rrr-cut",
        "content": (
            "中国人民银行今日宣布，自下月起下调金融机构存款准备金率 0.5 个百分点，"
            "预计释放长期流动性约 1 万亿元人民币。央行表示，此举旨在保持银行体系"
            "流动性合理充裕，引导金融机构加大对实体经济的支持力度。分析人士认为，"
            "此次降准释放了明确的稳增长信号，A 股市场有望迎来新一轮上涨行情。"
        ),
        "source_name": "财经网",
        "language": "zh",
        "tags": ["央行", "降准", "货币政策"],
    },
    {
        "title": "美国对华芯片出口管制升级，涉及 AI 训练芯片",
        "url": "https://example.com/news/us-china-chip-ban",
        "content": (
            "美国商务部工业与安全局（BIS）今日发布新规，进一步收紧对华高端芯片"
            "出口管制。新规将限制范围扩大至 AI 训练芯片和先进封装技术。中国商务部"
            "回应称，美方泛化国家安全概念，滥用出口管制措施，中方将采取必要措施"
            "维护中国企业的正当权益。受此消息影响，国内半导体板块今日逆势上涨。"
        ),
        "source_name": "路透社",
        "language": "zh",
        "tags": ["芯片", "中美贸易", "制裁"],
    },
    {
        "title": "美联储维持利率不变，暗示年内可能降息两次",
        "url": "https://example.com/news/fed-rate-decision",
        "content": (
            "美联储 FOMC 会议决定维持联邦基金利率在 5.25%-5.50% 区间不变，"
            "符合市场预期。但最新点阵图显示，多数委员预计年内将降息两次，"
            "较此前的预测更为鸽派。美联储主席鲍威尔在新闻发布会上表示，"
            "通胀正在向 2% 目标靠近，但仍需更多数据确认。美股三大指数应声上涨。"
        ),
        "source_name": "华尔街见闻",
        "language": "zh",
        "tags": ["美联储", "利率", "美股"],
    },
    {
        "title": "中国自主研发 5nm 芯片实现量产突破",
        "url": "https://example.com/news/china-5nm-chip",
        "content": (
            "国内某头部芯片制造企业今日宣布，其自主研发的 5 纳米制程工艺芯片"
            "已实现小批量量产，良率达到 75% 以上。这标志着中国在先进制程领域"
            "取得了里程碑式突破。行业专家指出，虽然与国际最先进的 3nm 工艺仍有"
            "差距，但 5nm 量产能力将极大缓解国内高端芯片供应紧张的局面。"
        ),
        "source_name": "新华网",
        "language": "zh",
        "tags": ["芯片", "半导体", "国产替代"],
    },
    {
        "title": "地缘政治风险升温：中东局势再度紧张",
        "url": "https://example.com/news/mideast-tension",
        "content": (
            "中东地区局势近期再度紧张，多国展开外交斡旋。国际油价受此影响"
            "连续第三个交易日上涨，布伦特原油突破 85 美元/桶。分析人士警告，"
            "若局势进一步升级，全球能源供应链可能受到冲击，各国央行在制定"
            "货币政策时将面临更复杂的通胀压力考量。"
        ),
        "source_name": "BBC 中文",
        "language": "zh",
        "tags": ["地缘政治", "油价", "中东"],
    },
    {
        "title": "特斯拉 FSD v13 在中国获批测试许可",
        "url": "https://example.com/news/tesla-fsd-china",
        "content": (
            "特斯拉全自动驾驶系统 FSD v13 版本已获得中国相关部门批准，"
            "将在上海、北京等城市开展公开道路测试。这是特斯拉 FSD 首次在中国"
            "获得公开道路测试许可。业内认为，这将加速国内智能驾驶技术的竞争"
            "与迭代，对蔚来、小鹏、华为等本土厂商形成新的竞争压力。"
        ),
        "source_name": "36氪",
        "language": "zh",
        "tags": ["自动驾驶", "特斯拉", "新能源"],
    },
    {
        "title": "全球外汇市场波动加剧，人民币汇率承压",
        "url": "https://example.com/news/forex-volatility",
        "content": (
            "受美联储政策预期和地缘政治因素影响，全球外汇市场近期波动显著加剧。"
            "人民币对美元汇率在岸价一度跌破 7.30 关口。央行货币政策委员会委员"
            "表示，人民币汇率具有坚实的基本面支撑，短期波动在正常范围内，"
            "央行有能力维护外汇市场平稳运行。"
        ),
        "source_name": "金融时报",
        "language": "zh",
        "tags": ["汇率", "人民币", "外汇"],
    },
]


async def collect(config: dict) -> list[RawArticle]:
    """
    返回模拟新闻数据

    config 格式（来自 sources.yaml）:
        {enabled, article_count}
    """
    settings = get_settings()
    if settings.app.APP_ENV == "production":
        logger.warning("模拟采集器在生产环境不可用，已跳过")
        return []

    count = config.get("article_count", 8)
    if "_topics" in config and config["_topics"]:
        topics = [t.lower() for t in config["_topics"]]
        # 按主题关键词过滤相关文章
        filtered = [
            a for a in _MOCK_ARTICLES
            if any(tag.lower() in " ".join(a["tags"]).lower() for tag in topics)
            or any(tag in a["title"] or tag in a["content"] for tag in topics)
        ]
        selected = filtered if filtered else _MOCK_ARTICLES
    else:
        selected = _MOCK_ARTICLES

    articles: list[RawArticle] = []
    now = datetime.now(timezone.utc)

    for i, item in enumerate(selected[:count]):
        published = now - timedelta(hours=i * 3)  # 每篇间隔 3 小时
        article = RawArticle(
            id=RawArticle.make_id(item["url"]),
            title=item["title"],
            url=item["url"],
            content=item["content"],
            summary=item["content"][:100],
            source="mock",
            source_name=item["source_name"],
            language=item.get("language", "zh"),
            published_at=published,
            metadata={"tags": item.get("tags", []), "is_mock": True},
        )
        articles.append(article)

    logger.info("模拟采集器: 生成 %d 篇模拟新闻", len(articles))
    return articles
