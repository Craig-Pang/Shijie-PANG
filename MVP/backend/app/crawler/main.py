"""
爬虫主程序入口
"""

import asyncio
import json
import sys
from datetime import datetime
from .powerchina_crawler import crawl_and_analyze


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='爬取并分析中国电建阳光采购网招标公告')
    parser.add_argument('--max-notices', type=int, default=10, help='最大爬取数量')
    parser.add_argument('--no-analyze', action='store_true', help='不进行 AI 分析')
    parser.add_argument('--delay', type=float, default=1.0, help='请求延迟（秒）')
    parser.add_argument('--output', type=str, help='输出 JSON 文件路径')
    parser.add_argument('--no-db', action='store_true', help='不保存到数据库')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("中国电建阳光采购网招标公告爬虫")
    print("=" * 60)
    print(f"最大数量: {args.max_notices}")
    print(f"AI 分析: {'否' if args.no_analyze else '是'}")
    print(f"请求延迟: {args.delay}秒")
    print("=" * 60)
    
    try:
        results = await crawl_and_analyze(
            max_notices=args.max_notices,
            analyze=not args.no_analyze,
            delay=args.delay,
            save_to_db=not args.no_db
        )
        
        # 输出结果
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"\n结果已保存到: {args.output}")
        else:
            # 打印摘要
            print("\n" + "=" * 60)
            print("爬取结果摘要")
            print("=" * 60)
            for i, result in enumerate(results, 1):
                print(f"\n{i}. {result.get('title', 'N/A')[:60]}")
                print(f"   URL: {result.get('url', 'N/A')}")
                if result.get('analysis'):
                    analysis = result['analysis']
                    print(f"   评分: {analysis.get('fit_score')}/100")
                    print(f"   标签: {analysis.get('fit_label')}")
                    print(f"   摘要: {analysis.get('summary', '')[:100]}...")
        
        print(f"\n\n共处理 {len(results)} 条公告")
        
    except KeyboardInterrupt:
        print("\n\n用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

