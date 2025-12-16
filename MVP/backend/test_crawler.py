#!/usr/bin/env python3
"""
测试爬虫脚本
"""

import sys
import asyncio
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from app.crawler import crawl_and_analyze


async def test():
    """测试爬虫"""
    print("=" * 60)
    print("开始测试爬虫...")
    print("=" * 60)
    
    try:
        # 只爬取 2 条，不进行 AI 分析（更快）
        results = await crawl_and_analyze(
            max_notices=2,
            analyze=False,  # 先不分析，测试爬取功能
            delay=2.0
        )
        
        print(f"\n\n共获取 {len(results)} 条公告\n")
        
        for i, result in enumerate(results, 1):
            print(f"{'='*60}")
            print(f"公告 {i}:")
            print(f"标题: {result.get('title', 'N/A')}")
            print(f"URL: {result.get('url', 'N/A')}")
            print(f"发布日期: {result.get('publish_date', 'N/A')}")
            
            extracted = result.get('extracted_fields', {})
            if extracted:
                print(f"\n提取的字段:")
                for key, value in extracted.items():
                    if value:
                        print(f"  {key}: {value}")
            
            raw_text = result.get('raw_text', '')
            if raw_text:
                print(f"\n正文预览: {raw_text[:200]}...")
            
            print()
        
        print("=" * 60)
        print("测试完成！")
        
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test())

