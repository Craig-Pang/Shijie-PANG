"""
使用 Playwright 获取渲染后的 HTML（仅用于获取，不解析）
"""

import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Browser, Page


class PlaywrightFetcher:
    """Playwright HTML 获取器（只负责获取渲染后的 HTML）"""
    
    def __init__(self, headless: bool = True, timeout: int = 30000, retries: int = 3):
        """
        初始化
        
        参数:
            headless: 是否无头模式
            timeout: 超时时间（毫秒）
            retries: 重试次数
        """
        self.headless = headless
        self.timeout = timeout
        self.retries = retries
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=self.headless)
        context = await self.browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        self.page = await context.new_page()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.browser:
            await self.browser.close()
    
    async def fetch_html(self, url: str) -> Optional[str]:
        """
        获取渲染后的 HTML
        
        参数:
            url: 目标 URL
        
        返回:
            HTML 内容，失败返回 None
        """
        if not self.page:
            raise RuntimeError("Page not initialized")
        
        last_error = None
        for attempt in range(1, self.retries + 1):
            try:
                print(f"[FETCH_MODE=playwright] 获取页面 (尝试 {attempt}/{self.retries}): {url}")
                
                await self.page.goto(url, wait_until='networkidle', timeout=self.timeout)
                
                # 等待内容加载
                await asyncio.sleep(2)  # 额外等待确保 JavaScript 执行完成
                
                # 获取渲染后的 HTML
                html = await self.page.content()
                
                if html and len(html) > 1000:  # 确保有实际内容
                    print(f"[FETCH_MODE=playwright] 成功获取 HTML ({len(html)} 字符)")
                    return html
                else:
                    print(f"[FETCH_MODE=playwright] HTML 内容过短，可能未正确加载")
                    
            except Exception as e:
                last_error = e
                print(f"[FETCH_MODE=playwright] 尝试 {attempt} 失败: {e}")
                if attempt < self.retries:
                    await asyncio.sleep(2)  # 重试前等待
        
        print(f"[FETCH_MODE=playwright] 所有尝试均失败: {last_error}")
        return None


async def fetch_with_playwright(
    url: str,
    headless: bool = True,
    timeout: int = 30000,
    retries: int = 3
) -> Optional[str]:
    """
    使用 Playwright 获取渲染后的 HTML
    
    参数:
        url: 目标 URL
        headless: 是否无头模式
        timeout: 超时时间（毫秒）
        retries: 重试次数
    
    返回:
        HTML 内容
    """
    try:
        async with PlaywrightFetcher(headless=headless, timeout=timeout, retries=retries) as fetcher:
            return await fetcher.fetch_html(url)
    except ImportError:
        print("[FETCH_MODE=playwright] 错误: 未安装 Playwright")
        print("请运行: pip install playwright && playwright install chromium")
        return None
    except Exception as e:
        print(f"[FETCH_MODE=playwright] 获取失败: {e}")
        return None
