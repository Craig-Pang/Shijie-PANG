"""
使用 Playwright 爬取 SPA 网站的爬虫
需要安装: pip install playwright && playwright install chromium
"""

import asyncio
from typing import List, Dict, Optional
from playwright.async_api import async_playwright, Browser, Page

from ..agent import analyze_notice


class PowerChinaCrawlerPlaywright:
    """使用 Playwright 的爬虫"""
    
    BASE_URL = "https://bid.powerchina.cn"
    NOTICE_LIST_URL = "https://bid.powerchina.cn/consult/notice"
    
    def __init__(self, headless: bool = True, delay: float = 2.0):
        """
        初始化
        
        参数:
            headless: 是否无头模式
            delay: 页面加载等待时间（秒）
        """
        self.headless = headless
        self.delay = delay
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=self.headless)
        context = await self.browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        self.page = await context.new_page()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.browser:
            await self.browser.close()
    
    async def wait_for_content(self, selector: str = None, timeout: int = 30000):
        """
        等待页面内容加载
        
        参数:
            selector: 等待的选择器
            timeout: 超时时间（毫秒）
        """
        if selector:
            await self.page.wait_for_selector(selector, timeout=timeout)
        else:
            # 等待网络空闲
            await self.page.wait_for_load_state('networkidle', timeout=timeout)
        
        # 额外等待，确保 JavaScript 执行完成
        await asyncio.sleep(self.delay)
    
    async def crawl_notice_list(self) -> List[Dict]:
        """
        爬取公告列表
        
        返回:
            公告列表
        """
        if not self.page:
            raise RuntimeError("Page not initialized")
        
        print(f"访问列表页: {self.NOTICE_LIST_URL}")
        await self.page.goto(self.NOTICE_LIST_URL, wait_until='networkidle')
        
        # 等待内容加载
        await self.wait_for_content()
        
        # 尝试多种选择器来查找公告列表
        notices = []
        
        # 方法1: 查找表格行
        rows = await self.page.query_selector_all('table tr, .notice-item, .list-item, [class*="notice"]')
        
        if rows:
            print(f"找到 {len(rows)} 个可能的列表项")
            for row in rows[:20]:  # 限制数量
                try:
                    # 查找链接
                    link = await row.query_selector('a[href]')
                    if link:
                        title = await link.inner_text()
                        href = await link.get_attribute('href')
                        
                        if title and href:
                            notice = {
                                'title': title.strip(),
                                'url': href if href.startswith('http') else f"{self.BASE_URL}{href}"
                            }
                            notices.append(notice)
                except:
                    continue
        
        # 方法2: 如果没找到，尝试从页面文本中提取
        if not notices:
            print("尝试从页面文本提取...")
            content = await self.page.content()
            
            # 这里可以添加更复杂的解析逻辑
            # 或者使用 JavaScript 执行来获取数据
            js_code = """
            () => {
                // 尝试从 window 对象获取数据
                if (window.__INITIAL_STATE__) {
                    return window.__INITIAL_STATE__;
                }
                if (window.app && window.app.$store) {
                    return window.app.$store.state;
                }
                return null;
            }
            """
            
            try:
                data = await self.page.evaluate(js_code)
                if data:
                    print(f"从 JavaScript 获取到数据: {type(data)}")
                    # 解析数据...
            except:
                pass
        
        # 方法3: 监听网络请求，查找 API 调用
        if not notices:
            print("尝试监听网络请求...")
            # 这里可以添加网络监听逻辑
        
        return notices
    
    async def crawl_notice_detail(self, notice: Dict) -> Optional[Dict]:
        """
        爬取公告详情
        
        参数:
            notice: 公告基本信息
        
        返回:
            完整公告数据
        """
        if not self.page:
            raise RuntimeError("Page not initialized")
        
        url = notice.get('url')
        if not url:
            return None
        
        print(f"  访问详情页: {url}")
        try:
            await self.page.goto(url, wait_until='networkidle', timeout=30000)
            await self.wait_for_content()
            
            # 提取标题
            title_elem = await self.page.query_selector('h1, h2, .title, [class*="title"]')
            title = await title_elem.inner_text() if title_elem else notice.get('title', '')
            
            # 提取正文
            content_elem = await self.page.query_selector('.content, .detail, article, [class*="content"]')
            if not content_elem:
                content_elem = await self.page.query_selector('body')
            
            raw_text = await content_elem.inner_text() if content_elem else ''
            
            # 提取字段（简化版，可以改进）
            extracted_fields = {}
            
            # 从页面中提取关键信息
            page_text = raw_text.lower()
            
            # 这里可以添加更详细的字段提取逻辑
            # 参考 powerchina_crawler.py 中的 parse_notice_detail 方法
            
            return {
                'title': title.strip(),
                'url': url,
                'raw_text': raw_text,
                'extracted_fields': extracted_fields
            }
        except Exception as e:
            print(f"  获取详情失败: {e}")
            return None


async def crawl_with_playwright(
    max_notices: int = 10,
    analyze: bool = True,
    headless: bool = True
) -> List[Dict]:
    """
    使用 Playwright 爬取并分析
    
    参数:
        max_notices: 最大数量
        analyze: 是否分析
        headless: 是否无头模式
    
    返回:
        结果列表
    """
    results = []
    
    try:
        async with PowerChinaCrawlerPlaywright(headless=headless) as crawler:
            print("开始爬取公告列表...")
            notices = await crawler.crawl_notice_list()
            print(f"找到 {len(notices)} 条公告")
            
            notices = notices[:max_notices]
            
            for i, notice in enumerate(notices, 1):
                print(f"\n处理公告 {i}/{len(notices)}: {notice.get('title', 'N/A')[:50]}...")
                
                detail = await crawler.crawl_notice_detail(notice)
                if not detail:
                    continue
                
                if analyze:
                    try:
                        analysis = await analyze_notice(
                            title=detail.get('title', ''),
                            url=detail.get('url', ''),
                            raw_text=detail.get('raw_text', ''),
                            extracted_fields=detail.get('extracted_fields', {})
                        )
                        detail['analysis'] = analysis
                        print(f"  分析完成: {analysis.get('fit_label')} ({analysis.get('fit_score')}/100)")
                    except Exception as e:
                        print(f"  AI 分析失败: {e}")
                
                results.append(detail)
    except ImportError:
        print("错误: 未安装 Playwright")
        print("请运行: pip install playwright && playwright install chromium")
    except Exception as e:
        print(f"爬取失败: {e}")
        import traceback
        traceback.print_exc()
    
    return results


if __name__ == "__main__":
    asyncio.run(crawl_with_playwright(max_notices=5))

