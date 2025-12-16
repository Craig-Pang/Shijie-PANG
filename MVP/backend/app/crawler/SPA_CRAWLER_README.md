# SPA 网站爬虫说明

## 问题分析

`bid.powerchina.cn` 是一个**单页应用（SPA）**，内容通过 JavaScript 动态加载，因此：
- 直接 HTTP 请求只能获取到空的 HTML 框架
- 需要使用浏览器引擎来渲染 JavaScript
- 或者找到实际的 API 接口

## 解决方案

### 方案 1: 使用 Playwright（推荐）

Playwright 可以模拟真实浏览器，渲染 JavaScript 并获取完整内容。

#### 安装依赖

```bash
pip install playwright
playwright install chromium
```

#### 使用 Playwright 爬虫

我已经创建了 `powerchina_crawler_playwright.py`，使用方法：

```python
from app.crawler.powerchina_crawler_playwright import crawl_with_playwright

results = await crawl_with_playwright(max_notices=10)
```

### 方案 2: 使用 Selenium

```bash
pip install selenium
# 需要下载 ChromeDriver
```

### 方案 3: 手动查找 API 接口

1. 打开浏览器开发者工具（F12）
2. 访问 https://bid.powerchina.cn/consult/notice
3. 在 Network 标签中查找 XHR/Fetch 请求
4. 找到实际的 API 接口 URL
5. 在代码中配置该接口

### 方案 4: 使用浏览器扩展

可以使用浏览器扩展（如 Web Scraper）来抓取数据。

## 当前状态

当前爬虫代码已经：
- ✅ 实现了基础框架
- ✅ 支持 API 接口查找
- ✅ 支持 HTML 解析（备用）
- ⚠️ 需要添加浏览器渲染支持（Playwright/Selenium）

## 下一步

如果需要立即使用，建议：
1. 安装 Playwright
2. 使用 Playwright 版本的爬虫
3. 或者手动查找 API 接口并配置

