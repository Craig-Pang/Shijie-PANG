# 中国电建阳光采购网爬虫

用于爬取 https://bid.powerchina.cn/consult/notice 的招标公告，并自动使用 AI agent 进行分析。

## 功能特性

- ✅ 爬取招标公告列表
- ✅ 爬取公告详情页
- ✅ 自动提取关键字段（地点、吨位、截止时间、资质要求等）
- ✅ 集成 AI agent 自动分析适配度
- ✅ 支持分页爬取
- ✅ 异步并发处理
- ✅ 可配置请求延迟

## 安装依赖

```bash
pip install -r requirements.txt
```

## 使用方法

### 1. 命令行使用

```bash
# 爬取 10 条公告并进行分析
python -m app.crawler.main --max-notices 10

# 爬取 20 条公告，不进行 AI 分析
python -m app.crawler.main --max-notices 20 --no-analyze

# 保存结果到 JSON 文件
python -m app.crawler.main --max-notices 10 --output results.json

# 设置请求延迟（避免请求过快）
python -m app.crawler.main --max-notices 10 --delay 2.0
```

### 2. 代码中使用

```python
import asyncio
from app.crawler import crawl_and_analyze

async def main():
    # 爬取并分析
    results = await crawl_and_analyze(
        max_notices=10,      # 最大爬取数量
        analyze=True,         # 是否进行 AI 分析
        delay=1.0            # 请求延迟（秒）
    )
    
    for result in results:
        print(f"标题: {result['title']}")
        if result.get('analysis'):
            analysis = result['analysis']
            print(f"  评分: {analysis['fit_score']}/100")
            print(f"  标签: {analysis['fit_label']}")

asyncio.run(main())
```

### 3. 单独使用爬虫类

```python
import asyncio
from app.crawler import PowerChinaCrawler

async def main():
    async with PowerChinaCrawler(delay=1.0) as crawler:
        # 爬取列表
        notices = await crawler.crawl_notice_list(max_pages=3)
        
        # 爬取详情
        for notice in notices[:5]:
            detail = await crawler.crawl_notice_detail(notice)
            print(detail)

asyncio.run(main())
```

## 输出数据结构

每条公告包含以下字段：

```python
{
    "title": "招标标题",
    "url": "公告链接",
    "publish_date": "发布日期",
    "raw_text": "公告正文（纯文本）",
    "extracted_fields": {
        "location": "项目地点",
        "tonnage": "钢结构吨位",
        "deadline": "投标截止时间",
        "qualification": "资质要求",
        "scope": "项目范围"
    },
    "analysis": {  # AI 分析结果（如果启用）
        "fit_score": 85,
        "fit_label": "RECOMMEND",
        "region_match": "HIGH",
        "scope_match": "HIGH",
        "scale_match": "MED",
        "qualification_match": "HIGH",
        "summary": "分析摘要",
        "reasons": ["原因1", "原因2"],
        "risk_flags": ["风险提示"],
        "key_fields": {
            "location": "...",
            "scope": "...",
            "deadline": "...",
            "tonnage": "...",
            "qualification": "..."
        }
    }
}
```

## 注意事项

1. **请求频率**：默认延迟 1 秒，避免请求过快被封禁
2. **网站结构变化**：如果网站 HTML 结构发生变化，可能需要调整解析逻辑
3. **AI 分析**：需要确保 Ollama 服务运行在 `http://localhost:11434`
4. **网络环境**：确保可以访问目标网站

## 环境变量

- `OLLAMA_BASE_URL`: Ollama 服务地址（默认: http://localhost:11434）
- `OLLAMA_MODEL`: 使用的模型名称（默认: qwen2.5:0.5b）

## 故障排除

### 无法获取页面
- 检查网络连接
- 检查网站是否可访问
- 尝试增加请求延迟

### AI 分析失败
- 检查 Ollama 服务是否运行
- 检查模型是否已下载
- 查看错误日志

### 解析失败
- 网站结构可能已变化
- 需要更新解析逻辑

