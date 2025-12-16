# 中国电建阳光采购网爬虫

用于爬取 https://bid.powerchina.cn/consult/notice 的招标公告，并自动使用 AI agent 进行分析。

## 功能特性

- ✅ 爬取招标公告列表
- ✅ 爬取公告详情页
- ✅ 自动提取关键字段（地点、吨位、截止时间、资质要求等）
- ✅ 集成 AI agent 自动分析适配度
- ✅ **自动 fallback 到 Playwright**（当 requests 无法获取内容时）
- ✅ 自动保存到数据库（notices 表）
- ✅ 支持分页爬取
- ✅ 异步并发处理
- ✅ 可配置请求延迟

## 安装依赖

### 1. 安装 Python 依赖

```bash
cd MVP/backend
pip install -r requirements.txt
```

### 2. 安装 Playwright 浏览器（必需）

由于目标网站是 SPA（单页应用），需要 Playwright 来渲染 JavaScript：

```bash
playwright install chromium
```

**注意**：首次运行会自动尝试安装，但建议提前安装以避免延迟。

## 使用方法

### 1. 命令行使用

```bash
# 爬取 10 条公告并进行分析，自动保存到数据库
python -m app.crawler.main --max-notices 10

# 爬取 20 条公告，不进行 AI 分析
python -m app.crawler.main --max-notices 20 --no-analyze

# 保存结果到 JSON 文件（不保存到数据库）
python -m app.crawler.main --max-notices 10 --output results.json --no-db

# 设置请求延迟（避免请求过快）
python -m app.crawler.main --max-notices 10 --delay 2.0
```

### 2. 代码中使用

```python
import asyncio
from app.crawler import crawl_and_analyze

async def main():
    # 爬取并分析，自动保存到数据库
    results = await crawl_and_analyze(
        max_notices=10,      # 最大爬取数量
        analyze=True,         # 是否进行 AI 分析
        delay=1.0,            # 请求延迟（秒）
        save_to_db=True      # 是否保存到数据库
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
        # 爬取列表（自动 fallback 到 Playwright）
        notices = await crawler.crawl_notice_list(max_pages=3)
        
        # 爬取详情（自动 fallback 到 Playwright）
        for notice in notices[:5]:
            detail = await crawler.crawl_notice_detail(notice)
            print(detail)

asyncio.run(main())
```

## Fallback 机制

爬虫采用智能 fallback 机制：

1. **首先尝试 requests**：使用 `aiohttp` 直接获取 HTML
   - 日志标识：`[FETCH_MODE=requests]`
   - 速度快，资源占用少

2. **自动 fallback 到 Playwright**：当以下情况发生时：
   - requests 获取失败
   - 获取的 HTML 内容为空或过短（< 1000 字符）
   - 日志标识：`[FETCH_MODE=playwright]`
   - 使用真实浏览器渲染 JavaScript

3. **复用解析逻辑**：无论使用哪种方式获取 HTML，都使用相同的解析逻辑

## 数据库结构

爬虫会自动将数据保存到 `notices` 表：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| title | String | 公告标题 |
| url | String | 公告链接（唯一） |
| published_at | DateTime | 发布日期 |
| raw_text | Text | 公告正文 |
| analysis_json | JSON | AI 分析结果 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

**注意**：如果公告已存在（根据 URL），会更新现有记录。

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

## 配置

### 环境变量

- `OLLAMA_BASE_URL`: Ollama 服务地址（默认: http://localhost:11434）
- `OLLAMA_MODEL`: 使用的模型名称（默认: qwen2.5:0.5b）
- `DATABASE_URL`: 数据库连接 URL（默认: sqlite:///./tender_notices.db）

### Playwright 配置

在代码中可以配置 Playwright 参数：

```python
from app.crawler.powerchina_crawler_playwright import fetch_with_playwright

html = await fetch_with_playwright(
    url="https://...",
    headless=True,      # 是否无头模式
    timeout=30000,       # 超时时间（毫秒）
    retries=3           # 重试次数
)
```

## 注意事项

1. **请求频率**：默认延迟 1 秒，避免请求过快被封禁
2. **Playwright 安装**：首次使用需要安装 Chromium 浏览器
3. **网站结构变化**：如果网站 HTML 结构发生变化，可能需要调整解析逻辑
4. **AI 分析**：需要确保 Ollama 服务运行在 `http://localhost:11434`
5. **网络环境**：确保可以访问目标网站
6. **数据库**：默认使用 SQLite，生产环境建议使用 PostgreSQL 或 MySQL

## 故障排除

### 无法获取页面

- 检查网络连接
- 检查网站是否可访问
- 查看日志中的 `[FETCH_MODE=...]` 标识，确认使用的获取方式
- 如果 requests 失败，会自动 fallback 到 Playwright

### Playwright 相关错误

- 确保已安装：`playwright install chromium`
- 检查系统是否支持 Chromium
- 查看错误日志

### AI 分析失败

- 检查 Ollama 服务是否运行
- 检查模型是否已下载
- 查看错误日志

### 数据库错误

- 检查数据库连接配置
- 确保有写入权限
- 查看错误日志

### 解析失败

- 网站结构可能已变化
- 需要更新解析逻辑
- 检查日志中的 HTML 内容

## 日志说明

爬虫会输出详细的日志，包括：

- `[FETCH_MODE=requests]`: 使用 requests 方式获取
- `[FETCH_MODE=playwright]`: 使用 Playwright 方式获取
- `[DB]`: 数据库操作日志

通过这些日志可以清楚地看到爬虫的工作流程。
