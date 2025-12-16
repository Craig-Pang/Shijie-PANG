"""
集成示例：展示如何在爬虫 pipeline 中使用 AI agent

使用方法：
1. 在爬虫处理新公告/更新公告时，调用 analyze_notice
2. 将返回的 analysis_json 写入数据库
"""

import asyncio
from .analyzer import analyze_notice


async def example_usage():
    """示例：分析一个招标公告"""
    
    # 模拟招标公告数据
    title = "四川成都某钢结构厂房建设项目招标公告"
    url = "https://example.com/tender/12345"
    raw_text = """
    项目名称：四川成都某钢结构厂房建设项目
    项目地点：四川省成都市高新区
    项目规模：约1000吨钢结构
    项目内容：钢结构厂房制作、安装、运输
    投标截止时间：2024年12月31日
    资质要求：钢结构工程专业承包贰级
    """
    
    extracted_fields = {
        "location": "四川省成都市高新区",
        "tonnage": "1000吨",
        "deadline": "2024年12月31日"
    }
    
    # 调用分析
    result = await analyze_notice(
        title=title,
        url=url,
        raw_text=raw_text,
        extracted_fields=extracted_fields
    )
    
    print("分析结果：")
    print(f"适配度评分: {result['fit_score']}/100")
    print(f"推荐标签: {result['fit_label']}")
    print(f"摘要: {result['summary']}")
    print(f"原因: {result['reasons']}")
    
    # 这里可以将 result 写入数据库
    # 例如：db.notices.update_one({url: url}, {"$set": {"analysis_json": result}})
    
    return result


# 在爬虫 pipeline 中的使用示例
async def process_new_notice(notice_data: dict):
    """
    处理新公告的示例函数
    
    参数:
        notice_data: 包含 title, url, content, extracted_fields 等的字典
    """
    try:
        analysis_result = await analyze_notice(
            title=notice_data.get("title", ""),
            url=notice_data.get("url", ""),
            raw_text=notice_data.get("content", "") or notice_data.get("raw_text", ""),
            extracted_fields=notice_data.get("extracted_fields")
        )
        
        # 将分析结果写入数据库
        # 注意：这里假设数据库模型有 analysis_json 字段
        # update_notice_analysis(notice_data["url"], analysis_result)
        
        return analysis_result
    except Exception as e:
        print(f"分析失败: {e}")
        return None


if __name__ == "__main__":
    # 运行示例
    asyncio.run(example_usage())

