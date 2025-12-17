"""
爬虫主程序入口
"""

import asyncio
import csv
import json
import os
import sys
from datetime import datetime
from .powerchina_crawler import crawl_and_analyze


def _export_results(results):
    """导出 CSV 和 Markdown 摘要（只包含 RECOMMEND / REVIEW）"""
    ts = datetime.now().strftime("%Y%m%d_%H")
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    exports_dir = os.path.join(base_dir, "exports")
    reports_dir = os.path.join(base_dir, "reports")
    os.makedirs(exports_dir, exist_ok=True)
    os.makedirs(reports_dir, exist_ok=True)

    # 过滤出有分析结果且标签为 RECOMMEND / REVIEW 的记录（排除 UNKNOWN）
    filtered = []
    for r in results:
        analysis = r.get("analysis") or {}
        decision_state = (analysis.get("decision_state") or analysis.get("fit_label") or "").upper()
        if decision_state in ("RECOMMEND", "REVIEW"):
            filtered.append(
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "published_at": r.get("published_at"),
                    "fit_score": analysis.get("fit_score"),  # 可能为 null
                    "fit_label": decision_state,
                    "decision_state": decision_state,
                    "summary": analysis.get("summary", ""),
                    "input_quality": analysis.get("_meta", {}).get("input_quality", "UNKNOWN"),
                    "decision_source": analysis.get("_meta", {}).get("decision_source", "UNKNOWN"),
                }
            )

    # 导出 CSV
    csv_path = os.path.join(exports_dir, f"recommend_{ts}.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["title", "url", "published_at", "fit_score", "fit_label", "decision_state", "input_quality", "decision_source", "summary"])
        for item in filtered:
            writer.writerow(
                [
                    item["title"],
                    item["url"],
                    item["published_at"],
                    item["fit_score"] if item["fit_score"] is not None else "",
                    item["fit_label"],
                    item.get("decision_state", item["fit_label"]),
                    item.get("input_quality", ""),
                    item.get("decision_source", ""),
                    item["summary"],
                ]
            )

    # 生成 Markdown 摘要
    md_path = os.path.join(reports_dir, f"digest_{ts}.md")
    total = len(results)
    recommend_count = sum(1 for r in results if (r.get("analysis") or {}).get("decision_state") == "RECOMMEND")
    review_count = sum(1 for r in results if (r.get("analysis") or {}).get("decision_state") == "REVIEW")
    skip_count = sum(1 for r in results if (r.get("analysis") or {}).get("decision_state") == "SKIP")
    unknown_count = sum(1 for r in results if (r.get("analysis") or {}).get("decision_state") == "UNKNOWN")
    
    # Top 10 按分数排序（null 分数排最后）
    top10 = sorted(
        filtered,
        key=lambda x: (x["fit_score"] if isinstance(x["fit_score"], int) else -1),
        reverse=True,
    )[:10]

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# 投标情报摘要 {ts}\n\n")
        f.write(f"## 概览\n\n")
        f.write(f"- 总处理公告数：{total}\n")
        f.write(f"- 推荐 (RECOMMEND)：{recommend_count}\n")
        f.write(f"- 需评审 (REVIEW)：{review_count}\n")
        f.write(f"- 跳过 (SKIP)：{skip_count}\n")
        f.write(f"- 信息不足 (UNKNOWN)：{unknown_count}\n\n")
        f.write("## Top 10 推荐/需评审项目\n\n")
        if not top10:
            f.write("暂无推荐或需评审项目。\n")
        else:
            for i, item in enumerate(top10, 1):
                f.write(f"{i}. **{item['title']}**  \n")
                f.write(f"   - URL: {item['url'] or '（无）'}  \n")
                score_str = f"{item['fit_score']}/100" if item['fit_score'] is not None else "null"
                f.write(f"   - 评分: {score_str}  \n")
                f.write(f"   - 标签: {item['fit_label']}  \n")
                f.write(f"   - 输入质量: {item.get('input_quality', 'UNKNOWN')}  \n")
                f.write(f"   - 决策来源: {item.get('decision_source', 'UNKNOWN')}  \n")
                if item["summary"]:
                    f.write(f"   - 摘要: {item['summary'][:200]}  \n")
                f.write("\n")

    print(f"\n导出 CSV：{csv_path}")
    print(f"生成摘要报告：{md_path}")


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="爬取并分析中国电建阳光采购网招标公告")
    parser.add_argument("--max-notices", type=int, default=10, help="最大爬取数量")
    parser.add_argument("--no-analyze", action="store_true", help="不进行 AI 分析")
    parser.add_argument("--delay", type=float, default=1.0, help="请求延迟（秒）")
    parser.add_argument("--output", type=str, help="输出 JSON 文件路径")
    parser.add_argument("--no-db", action="store_true", help="不保存到数据库")

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
            save_to_db=not args.no_db,
        )

        # 输出结果 / 导出摘要
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"\n结果已保存到: {args.output}")
        else:
            print("\n" + "=" * 60)
            print("爬取结果摘要")
            print("=" * 60)
            for i, result in enumerate(results, 1):
                print(f"\n{i}. {result.get('title', 'N/A')[:60]}")
                print(f"   URL: {result.get('url', 'N/A')}")
                if result.get("analysis"):
                    analysis = result["analysis"]
                    print(f"   评分: {analysis.get('fit_score')}/100")
                    print(f"   标签: {analysis.get('fit_label')}")
                    print(f"   摘要: {analysis.get('summary', '')[:100]}...")

        print(f"\n\n共处理 {len(results)} 条公告")

        # 导出 CSV 和 Markdown 摘要（仅当启用分析时才有意义）
        if not args.no_analyze and results:
            _export_results(results)

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

