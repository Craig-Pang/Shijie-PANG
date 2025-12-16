"""
使用 Playwright 获取渲染后的 HTML 或从 JS 变量获取公告列表
包含详情获取器
"""

import asyncio
import hashlib
import re
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
                
                await self.page.goto(url, wait_until='networkidle', timeout=self.timeout)
                await self.page.wait_for_timeout(1500)
                
                final_url = self.page.url
                if final_url != url:
                    print(f"[FETCH_MODE=playwright] 检测到重定向: {url} -> {final_url}")
                
                html = await self.page.content()
                
                if debug:
                    print(f"[FETCH_MODE=playwright] 最终 URL: {final_url}")
                    print(f"[FETCH_MODE=playwright] HTML 前 500 字: {html[:500]}")
                    try:
                        await self.page.screenshot(path="debug_playwright.png")
                        print(f"[FETCH_MODE=playwright] 截图已保存: debug_playwright.png")
                    except:
                        pass
                
                if html and len(html) > 1000:
                    print(f"[FETCH_MODE=playwright] 成功获取 HTML ({len(html)} 字符)")
                    return (html, final_url)
                else:
                    print(f"[FETCH_MODE=playwright] HTML 内容过短 ({len(html) if html else 0} 字符)")
                    
            except Exception as e:
                last_error = e
                print(f"[FETCH_MODE=playwright] 尝试 {attempt} 失败: {e}")
                if attempt < self.retries:
                    await asyncio.sleep(2)
        
        print(f"[FETCH_MODE=playwright] 所有尝试均失败: {last_error}")
        return None
    
    def extract_source_item_id(self, row_element) -> Optional[str]:
        """
        从 DOM 元素中提取 source_item_id
        
        参数:
            row_element: 行元素（可以是 BeautifulSoup 元素或 Playwright Locator）
        
        返回:
            source_item_id 或 None
        """
        # 方法1: 查找 data-id 属性
        if hasattr(row_element, 'get'):
            # BeautifulSoup 元素
            item_id = row_element.get('data-id') or row_element.get('data-item-id') or row_element.get('data-notice-id')
            if item_id:
                return str(item_id)
            
            # 方法2: 从 onclick 中提取
            onclick = row_element.get('onclick', '')
            if onclick:
                # 尝试提取 ID（如 onclick="viewDetail('123')"）
                match = re.search(r"['\"](\d+)['\"]", onclick)
                if match:
                    return match.group(1)
            
            # 方法3: 查找隐藏字段
            hidden_inputs = row_element.find_all('input', type='hidden')
            for input_elem in hidden_inputs:
                if 'id' in input_elem.get('name', '').lower() or 'id' in input_elem.get('id', '').lower():
                    value = input_elem.get('value')
                    if value:
                        return str(value)
        
        return None
    
    async def fetch_detail_by_id(self, item_id: str, base_url: str = "https://bid.powerchina.cn") -> Optional[str]:
        """
        通过推导的详情接口获取详情
        
        参数:
            item_id: 项目ID
            base_url: 基础URL
        
        返回:
            详情 HTML 或文本，失败返回 None
        """
        if not self.page:
            raise RuntimeError("Page not initialized")
        
        # 尝试多种可能的详情接口
        detail_urls = [
            f"{base_url}/consult/notice/detail/{item_id}",
            f"{base_url}/api/consult/notice/detail/{item_id}",
            f"{base_url}/api/notice/detail/{item_id}",
            f"{base_url}/consult/api/notice/{item_id}",
        ]
        
        for detail_url in detail_urls:
            try:
                print(f"[DETAIL_FETCHER] 尝试详情接口: {detail_url}")
                await self.page.goto(detail_url, wait_until='networkidle', timeout=30000)
                await self.page.wait_for_timeout(1000)
                
                html = await self.page.content()
                if html and len(html) > 5000:  # 有实际内容
                    print(f"[DETAIL_FETCHER] 成功从接口获取详情 ({len(html)} 字符)")
                    return html
            except Exception as e:
                print(f"[DETAIL_FETCHER] 接口 {detail_url} 失败: {e}")
                continue
        
        return None
    
    async def fetch_detail_by_click(self, row_selector: str, list_url: str) -> Optional[str]:
        """
        通过点击列表项获取详情
        
        参数:
            row_selector: 行选择器
            list_url: 列表页 URL
        
        返回:
            详情 HTML 或文本，失败返回 None
        """
        if not self.page:
            raise RuntimeError("Page not initialized")
        
        try:
            # 确保在列表页
            if self.page.url != list_url:
                await self.page.goto(list_url, wait_until='networkidle', timeout=self.timeout)
                await self.page.wait_for_timeout(2000)
            
            # 尝试多种点击方式
            print(f"[DETAIL_FETCHER] 尝试点击列表项: {row_selector}")
            
            # 方法1: 直接点击行
            try:
                row_locator = self.page.locator(row_selector).first
                await row_locator.click(timeout=5000)
                await self.page.wait_for_timeout(2000)
            except:
                # 方法2: 点击行内的标题或链接
                try:
                    title_locator = self.page.locator(f'{row_selector} .title, {row_selector} a, {row_selector} .cell').first
                    await title_locator.click(timeout=5000)
                    await self.page.wait_for_timeout(2000)
                except:
                    print(f"[DETAIL_FETCHER] 点击失败，尝试其他方法")
            
            # 检查 URL 是否变化（可能跳转到详情页）
            current_url = self.page.url
            if current_url != list_url:
                print(f"[DETAIL_FETCHER] 检测到 URL 变化: {current_url}")
                html = await self.page.content()
                if html and len(html) > 5000:
                    print(f"[DETAIL_FETCHER] 从新页面获取详情 ({len(html)} 字符)")
                    return html
            
            # 尝试多种选择器查找详情区域（弹窗或展开内容）
            detail_selectors = [
                '.el-dialog__body',
                '.el-drawer__body',
                '.detail-content',
                '.notice-detail',
                '.content-detail',
                '[class*="detail"]',
                '[class*="content"]',
                'article',
                '.modal-body',
                '.dialog-content',
                '.el-table__expanded-cell'
            ]
            
            for selector in detail_selectors:
                try:
                    detail_elem = await self.page.wait_for_selector(selector, timeout=2000, state='visible')
                    if detail_elem:
                        detail_text = await detail_elem.inner_text()
                        if detail_text and len(detail_text) > 100:
                            print(f"[DETAIL_FETCHER] 成功从点击获取详情 (选择器: {selector}, {len(detail_text)} 字符)")
                            return detail_text
                except:
                    continue
            
            # 如果没找到详情区域，获取整个页面内容（可能详情已展开）
            html = await self.page.content()
            # 检查页面是否包含更多内容（相比列表页）
            if html and len(html) > 100000:  # 详情页通常比列表页大
                print(f"[DETAIL_FETCHER] 从页面获取详情 ({len(html)} 字符)")
                return html
            
            print(f"[DETAIL_FETCHER] 点击后未找到详情内容")
            return None
            
        except Exception as e:
            print(f"[DETAIL_FETCHER] 点击获取详情失败: {e}")
            import traceback
            traceback.print_exc()
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


async def fetch_detail_with_playwright(
    item_id: Optional[str],
    row_selector: Optional[str],
    list_url: str,
    base_url: str = "https://bid.powerchina.cn",
    headless: bool = True,
    timeout: int = 60000
) -> Optional[str]:
    """
    获取详情（优先推导接口，否则点击）
    
    参数:
        item_id: 项目ID（用于推导接口）
        row_selector: 行选择器（用于点击）
        list_url: 列表页 URL
        base_url: 基础URL
        headless: 是否无头模式
        timeout: 超时时间
    
    返回:
        详情 HTML 或文本
    """
    try:
        async with PlaywrightFetcher(headless=headless, timeout=timeout, retries=2) as fetcher:
            # 优先尝试推导接口
            if item_id:
                detail = await fetcher.fetch_detail_by_id(item_id, base_url)
                if detail:
                    return detail
            
            # 如果接口失败，尝试点击
            if row_selector:
                detail = await fetcher.fetch_detail_by_click(row_selector, list_url)
                if detail:
                    return detail
            
            return None
    except ImportError:
        print("[DETAIL_FETCHER] 错误: 未安装 Playwright")
        return None
    except Exception as e:
        print(f"[DETAIL_FETCHER] 获取详情失败: {e}")
        return None
