"""测试 DeepSeek API 是否畅通"""
import asyncio, httpx, time

async def main():
    # 从容器环境变量读取
    api_key = "sk-61ef8c8539344f0cb1f5a18d57165816"
    url = "https://api.deepseek.com/v1/chat/completions"

    async with httpx.AsyncClient(timeout=60) as c:
        for size in ["short", "long"]:
            t0 = time.monotonic()
            try:
                payload = {
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": "你是一名审核编辑。请用中文简短回答。"},
                        {"role": "user", "content": "请审核以下文本，输出通过/不通过:\n测试内容：AI行业今天发布了新产品。" if size == "short" else "请审核以下研报内容（模拟）:\n" + "这是一份关于AI行业的深度研报。\n" * 50},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 256 if size == "short" else 1024,
                }
                resp = await c.post(url, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json=payload)
                elapsed = time.monotonic() - t0
                print(f"[{size}] HTTP {resp.status_code}, 耗时 {elapsed:.1f}s")
                if resp.status_code == 200:
                    data = resp.json()
                    print(f"  回复: {data['choices'][0]['message']['content'][:100]}...")
                else:
                    print(f"  错误: {resp.text[:300]}")
            except Exception as e:
                elapsed = time.monotonic() - t0
                print(f"[{size}] 失败 ({elapsed:.1f}s): {e}")

asyncio.run(main())
