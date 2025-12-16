"""
使用 Playwright 获取渲染后的 HTML 或从 JS 变量获取公告列表
只负责获取，不解析
"""

import asyncio
import hashlib
from typing import List, Dict, Optional, Tuple
from playwright.async_api import async_playwright, Browser, Page
from datetime import datetime


class PlaywrightFetcher:
    """Playwright HTML 获取器（只负责获取渲染后的 HTML 或列表数据）"""
    
    def __init__(self, headless: bool = True, timeout: int = 60000, retries: int = 2):
        """
        初始化
        
        参数:
            headless: 是否无头模式（默认 True，CI/服务器更稳）
            timeout: 超时时间（毫秒，默认 60000）
            retries: 重试次数（默认 2 次）
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
    
    async def fetch_html(self, url: str, debug: bool = False) -> Optional[Tuple[str, str]]:
        """
        获取渲染后的 HTML
        
        参数:
            url: 目标 URL
            debug: 是否输出调试信息
        
        返回:
            (html, final_url) 元组，失败返回 None
        """
        if not self.page:
            raise RuntimeError("Page not initialized")
        
        last_error = None
        for attempt in range(1, self.retries + 1):
            try:
                print(f"[FETCH_MODE=playwright] 获取页面 (尝试 {attempt}/{self.retries}): {url}")
                
                # 使用 networkidle 和长超时
                await self.page.goto(url, wait_until='networkidle', timeout=self.timeout)
                
                # 等待额外时间确保 JavaScript 执行完成（很多 SPA networkidle 还不够）
                await self.page.wait_for_timeout(1500)  # 1.5 秒
                
                # 获取最终 URL（防止重定向）
                final_url = self.page.url
                if final_url != url:
                    print(f"[FETCH_MODE=playwright] 检测到重定向: {url} -> {final_url}")
                
                # 获取渲染后的 HTML
                html = await self.page.content()
                
                # 调试输出
                if debug:
                    print(f"[FETCH_MODE=playwright] 最终 URL: {final_url}")
                    print(f"[FETCH_MODE=playwright] HTML 前 500 字: {html[:500]}")
                    # 可选截图
                    try:
                        await self.page.screenshot(path="debug_playwright.png")
                        print(f"[FETCH_MODE=playwright] 截图已保存: debug_playwright.png")
                    except:
                        pass
                
                if html and len(html) > 1000:
                    print(f"[FETCH_MODE=playwright] 成功获取 HTML ({len(html)} 字符)")
                    return (html, final_url)
                else:
                    print(f"[FETCH_MODE=playwright] HTML 内容过短 ({len(html) if html else 0} 字符)，可能未正确加载")
                    
            except Exception as e:
                last_error = e
                print(f"[FETCH_MODE=playwright] 尝试 {attempt} 失败: {e}")
                if attempt < self.retries:
                    await asyncio.sleep(2)  # 重试前等待
        
        print(f"[FETCH_MODE=playwright] 所有尝试均失败: {last_error}")
        return None
    
    async def fetch_notice_list_from_js(self, url: str) -> Optional[List[Dict]]:
        """
        从页面 JS 变量或请求结果获取公告列表
        
        参数:
            url: 列表页 URL
        
        返回:
            公告列表 [{title, url, published_at, html_or_text}]，失败返回 None
        """
        if not self.page:
            raise RuntimeError("Page not initialized")
        
        try:
            print(f"[FETCH_MODE=playwright] 尝试从 JS 获取公告列表: {url}")
            
            await self.page.goto(url, wait_until='networkidle', timeout=self.timeout)
            await self.page.wait_for_timeout(1500)
            
            # 方法1: 尝试从 window 对象获取数据
            js_code = """
            () => {
                // 尝试多种可能的全局变量
                if (window.__INITIAL_STATE__) {
                    return {type: 'initial_state', data: window.__INITIAL_STATE__};
                }
                if (window.app && window.app.$store && window.app.$store.state) {
                    return {type: 'vuex', data: window.app.$store.state};
                }
                if (window.__NUXT__) {
                    return {type: 'nuxt', data: window.__NUXT__};
                }
                if (window.__NEXT_DATA__) {
                    return {type: 'next', data: window.__NEXT_DATA__};
                }
                // 尝试查找列表数据
                const scripts = document.querySelectorAll('script');
                for (let script of scripts) {
                    const text = script.textContent || script.innerText;
                    if (text.includes('notice') || text.includes('tender') || text.includes('list')) {
                        try {
                            const match = text.match(/\\[.*?\\]/);
                            if (match) {
                                return {type: 'script', data: JSON.parse(match[0])};
                            }
                        } catch(e) {}
                    }
                }
                return null;
            }
            """
            
            result = await self.page.evaluate(js_code)
            if result and result.get('data'):
                print(f"[FETCH_MODE=playwright] 从 JS 获取到数据: {result['type']}")
                # 这里可以进一步解析 result['data'] 提取列表
                # 暂时返回 None，让调用方使用 HTML 解析
                return None
            
            # 方法2: 监听网络请求，查找 API 响应
            # 这里可以添加网络监听逻辑
            
            return None
            
        except Exception as e:
            print(f"[FETCH_MODE=playwright] 从 JS 获取列表失败: {e}")
            return None


async def fetch_html_with_playwright(
    url: str,
    headless: bool = True,
    timeout: int = 60000,
    retries: int = 2,
    debug: bool = False
) -> Optional[Tuple[str, str]]:
    """
    使用 Playwright 获取渲染后的 HTML
    
    参数:
        url: 目标 URL
        headless: 是否无头模式（默认 True）
        timeout: 超时时间（毫秒，默认 60000）
        retries: 重试次数（默认 2 次）
        debug: 是否输出调试信息
    
    返回:
        (html, final_url) 元组，失败返回 None
    """
    try:
        async with PlaywrightFetcher(headless=headless, timeout=timeout, retries=retries) as fetcher:
            return await fetcher.fetch_html(url, debug=debug)
    except ImportError:
        print("[FETCH_MODE=playwright] 错误: 未安装 Playwright")
        print("请运行: pip install playwright && playwright install chromium")
        return None
    except Exception as e:
        print(f"[FETCH_MODE=playwright] 获取失败: {e}")
        return None


async def fetch_notice_list_with_playwright(
    url: str,
    headless: bool = True,
    timeout: int = 60000,
    retries: int = 2
) -> Optional[List[Dict]]:
    """
    使用 Playwright 从页面获取公告列表（从 JS 变量或请求结果）
    
    参数:
        url: 列表页 URL
        headless: 是否无头模式
        timeout: 超时时间
        retries: 重试次数
    
    返回:
        公告列表 [{title, url, published_at, html_or_text}]，失败返回 None
    """
    try:
        async with PlaywrightFetcher(headless=headless, timeout=timeout, retries=retries) as fetcher:
            return await fetcher.fetch_notice_list_from_js(url)
    except ImportError:
        print("[FETCH_MODE=playwright] 错误: 未安装 Playwright")
        return None
    except Exception as e:
        print(f"[FETCH_MODE=playwright] 获取列表失败: {e}")
        return None
