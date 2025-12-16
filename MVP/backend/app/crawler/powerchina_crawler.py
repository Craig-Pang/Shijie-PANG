"""
中国电建阳光采购网爬虫
Pipeline: crawler -> extract -> hash去重 -> NEW/UPDATED -> analyze -> 入库
"""

import re
import asyncio
import hashlib
import aiohttp
from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from urllib.parse import urljoin

from ..agent import analyze_notice
from ..db import save_notice, get_notice_by_url, init_db
from .powerchina_crawler_playwright import fetch_html_with_playwright, fetch_notice_list_with_playwright


class PowerChinaCrawler:
    """中国电建阳光采购网爬虫"""
    
    BASE_URL = "https://bid.powerchina.cn"
    NOTICE_LIST_URL = "https://bid.powerchina.cn/consult/notice"
    
    API_PATHS = [
        "/api/consult/notice/list",
        "/api/notice/list",
        "/api/tender/list",
        "/consult/api/notice/list",
    ]
    
    def __init__(self, delay: float = 1.0, use_playwright_fallback: bool = True):
        """
        初始化爬虫
        
        参数:
            delay: 请求间隔（秒）
            use_playwright_fallback: 是否启用 Playwright fallback
        """
        self.delay = delay
        self.use_playwright_fallback = use_playwright_fallback
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://bid.powerchina.cn/consult/notice',
            'Origin': 'https://bid.powerchina.cn',
        }
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(headers=headers, timeout=timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.session:
            await self.session.close()
    
    async def fetch_page(self, url: str, use_fallback: bool = True) -> Optional[Tuple[str, str]]:
        """
        获取网页内容（带 fallback）
        
        参数:
            url: 目标 URL
            use_fallback: 是否在失败时使用 Playwright fallback
        
        返回:
            (html, final_url) 元组，失败返回 None
        """
        # 首先尝试 requests 方式
        print(f"[FETCH_MODE=requests] 获取页面: {url}")
        html = await self._fetch_with_requests(url)
        
        # 检查内容是否有效
        if html and len(html) > 1000:
            print(f"[FETCH_MODE=requests] 成功获取 HTML ({len(html)} 字符)")
            return (html, url)
        
        # 如果失败且启用 fallback，使用 Playwright
        if (not html or len(html) <= 1000) and use_fallback and self.use_playwright_fallback:
            print(f"[FETCH_MODE=requests] 获取失败或内容为空，fallback 到 Playwright")
            result = await fetch_html_with_playwright(url, headless=True, timeout=60000, retries=2, debug=True)
            if result:
                html, final_url = result
                if html and len(html) > 1000:
                    return (html, final_url)
        
        return None
    
    async def _fetch_with_requests(self, url: str) -> Optional[str]:
        """使用 requests 获取页面"""
        if not self.session:
            raise RuntimeError("Session not initialized.")
        
        try:
            await asyncio.sleep(self.delay)
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    print(f"[FETCH_MODE=requests] 请求失败: {url}, 状态码: {response.status}")
                    return None
        except Exception as e:
            print(f"[FETCH_MODE=requests] 获取页面失败 {url}: {e}")
            return None
    
    async def fetch_api(self, url: str, params: Dict = None) -> Optional[Dict]:
        """尝试调用 API 接口"""
        if not self.session:
            raise RuntimeError("Session not initialized.")
        
        try:
            await asyncio.sleep(self.delay)
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    content_type = response.headers.get('Content-Type', '')
                    if 'application/json' in content_type:
                        return await response.json()
                    else:
                        text = await response.text()
                        try:
                            import json
                            return json.loads(text)
                        except:
                            return None
                else:
                    return None
        except Exception as e:
            print(f"[FETCH_MODE=requests] API 调用失败 {url}: {e}")
            return None
    
    async def find_api_endpoint(self) -> Optional[str]:
        """尝试查找实际的 API 接口"""
        for api_path in self.API_PATHS:
            api_url = urljoin(self.BASE_URL, api_path)
            test_params = [
                {'page': 1, 'pageSize': 10},
                {'pageNo': 1, 'pageSize': 10},
                {'current': 1, 'size': 10},
            ]
            
            for params in test_params:
                result = await self.fetch_api(api_url, params)
                if result and isinstance(result, dict):
                    if 'data' in result or 'list' in result or 'records' in result:
                        print(f"[FETCH_MODE=requests] 找到 API 接口: {api_url}")
                        return api_url
        
        return None
    
    def parse_api_response(self, data: Dict) -> List[Dict]:
        """解析 API 响应数据，返回 [{title, url, published_at, html_or_text}]"""
        notices = []
        items = None
        
        if 'data' in data:
            if isinstance(data['data'], list):
                items = data['data']
            elif isinstance(data['data'], dict) and 'list' in data['data']:
                items = data['data']['list']
            elif isinstance(data['data'], dict) and 'records' in data['data']:
                items = data['data']['records']
        elif 'list' in data:
            items = data['list']
        elif 'records' in data:
            items = data['records']
        elif isinstance(data, list):
            items = data
        
        if not items:
            return notices
        
        for item in items:
            notice = {
                'title': item.get('title') or item.get('noticeTitle') or item.get('name') or '',
                'url': item.get('url') or item.get('link') or item.get('detailUrl') or '',
                'published_at': None,
                'html_or_text': item.get('content') or item.get('summary') or ''  # 如果有内容
            }
            
            if notice['url'] and not notice['url'].startswith('http'):
                notice['url'] = urljoin(self.BASE_URL, notice['url'])
            
            # 解析日期
            date_field = item.get('publishDate') or item.get('createTime') or item.get('date') or item.get('publishTime') or ''
            if date_field:
                try:
                    date_str = str(date_field)[:10]
                    for fmt in ['%Y-%m-%d', '%Y/%m/%d']:
                        try:
                            notice['published_at'] = datetime.strptime(date_str, fmt)
                            break
                        except:
                            continue
                except:
                    pass
            
            notice_id = item.get('id') or item.get('noticeId') or item.get('tenderId') or ''
            if notice_id and not notice['url']:
                notice['url'] = f"{self.BASE_URL}/consult/notice/{notice_id}"
            
            if notice.get('title') and notice.get('url'):
                notices.append(notice)
        
        return notices
    
    def parse_notice_list(self, html: str) -> List[Dict]:
        """
        解析招标公告列表页，返回 [{title, url, published_at, html_or_text}]
        """
        soup = BeautifulSoup(html, 'html.parser')
        notices = []
        
        # 查找表格行
        table_rows = soup.find_all('tr')
        for row in table_rows:
            links = row.find_all('a', href=True)
            if not links:
                continue
            
            notice = {
                'title': '',
                'url': '',
                'published_at': None,
                'html_or_text': ''
            }
            
            title_link = links[0]
            notice['title'] = title_link.get_text(strip=True)
            notice['url'] = urljoin(self.BASE_URL, title_link['href'])
            
            # 提取日期
            date_cells = row.find_all('td')
            for cell in date_cells:
                text = cell.get_text(strip=True)
                date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', text)
                if date_match:
                    date_str = date_match.group(1)
                    for fmt in ['%Y-%m-%d', '%Y/%m/%d']:
                        try:
                            notice['published_at'] = datetime.strptime(date_str, fmt)
                            break
                        except:
                            continue
                    break
            
            if notice.get('title') and notice.get('url'):
                notices.append(notice)
        
        return notices
    
    def extract_raw_text(self, html: str) -> str:
        """
        从 HTML 提取纯文本（extract -> raw_text）
        
        参数:
            html: HTML 内容
        
        返回:
            纯文本内容
        """
        soup = BeautifulSoup(html, 'html.parser')
        
        # 提取标题
        title_elem = soup.find(['h1', 'h2', 'h3'], class_=re.compile(r'title|head', re.I))
        if not title_elem:
            title_elem = soup.find('title')
        
        # 提取正文内容
        content_elem = soup.find(['div', 'article', 'section'], class_=re.compile(r'content|detail|main|body', re.I))
        if not content_elem:
            content_elem = soup.find('body')
        
        if content_elem:
            for script in content_elem(["script", "style", "nav", "header", "footer"]):
                script.decompose()
            return content_elem.get_text(separator='\n', strip=True)
        
        return ''
    
    async def crawl_notice_list(self, max_pages: int = 5) -> List[Dict]:
        """
        爬取公告列表，返回 [{title, url, published_at, html_or_text}]
        """
        all_notices = []
        
        # 尝试 API 接口
        api_url = await self.find_api_endpoint()
        
        if api_url:
            print(f"[FETCH_MODE=requests] 使用 API 接口: {api_url}")
            for page in range(1, max_pages + 1):
                params_list = [
                    {'page': page, 'pageSize': 20},
                    {'pageNo': page, 'pageSize': 20},
                    {'current': page, 'size': 20},
                ]
                
                page_notices = []
                for params in params_list:
                    data = await self.fetch_api(api_url, params)
                    if data:
                        page_notices = self.parse_api_response(data)
                        if page_notices:
                            all_notices.extend(page_notices)
                            break
                
                if not page_notices:
                    break
        else:
            # 首先尝试从 Playwright 获取列表（从 JS 变量）
            if self.use_playwright_fallback:
                js_list = await fetch_notice_list_with_playwright(
                    self.NOTICE_LIST_URL, headless=True, timeout=60000, retries=2
                )
                if js_list:
                    all_notices.extend(js_list)
                    return all_notices
            
            # 使用 HTML 解析（带 fallback）
            print(f"[FETCH_MODE=requests] 尝试 HTML 解析列表页...")
            result = await self.fetch_page(self.NOTICE_LIST_URL, use_fallback=True)
            if result:
                html, _ = result
                notices = self.parse_notice_list(html)
                all_notices.extend(notices)
        
        return all_notices
    
    async def crawl_notice_detail(self, notice: Dict) -> Optional[Dict]:
        """
        爬取单个公告详情，返回 {title, url, published_at, html_or_text}
        """
        url = notice.get('url')
        if not url:
            return None
        
        # 如果已有 html_or_text，直接使用
        if notice.get('html_or_text'):
            return {
                'title': notice.get('title', ''),
                'url': url,
                'published_at': notice.get('published_at'),
                'html_or_text': notice.get('html_or_text')
            }
        
        # 否则获取详情页
        result = await self.fetch_page(url, use_fallback=True)
        if not result:
            return None
        
        html, final_url = result
        return {
            'title': notice.get('title', ''),
            'url': final_url,  # 使用最终 URL（可能被重定向）
            'published_at': notice.get('published_at'),
            'html_or_text': html
        }


def calculate_content_hash(raw_text: str) -> str:
    """
    计算内容 hash（用于去重）
    
    参数:
        raw_text: 正文内容
    
    返回:
        hash 字符串
    """
    return hashlib.md5(raw_text.encode('utf-8')).hexdigest()


async def crawl_and_analyze(
    max_notices: int = 10,
    analyze: bool = True,
    delay: float = 1.0,
    save_to_db: bool = True
) -> List[Dict]:
    """
    完整的爬取和分析 pipeline
    
    Pipeline:
    1. crawler 返回 [{title, url, published_at, html_or_text}]
    2. extract -> raw_text
    3. hash 去重/更新
    4. NEW/UPDATED -> analyze_notice(...) -> analysis_json
    5. 写入数据库
    
    参数:
        max_notices: 最大爬取数量
        analyze: 是否使用 AI agent 分析
        delay: 请求延迟（秒）
        save_to_db: 是否保存到数据库
    
    返回:
        处理结果列表
    """
    # 初始化数据库
    if save_to_db:
        init_db()
    
    results = []
    
    async with PowerChinaCrawler(delay=delay) as crawler:
        # Step 1: 爬取列表，返回 [{title, url, published_at, html_or_text}]
        print(f"开始爬取招标公告列表...")
        notices = await crawler.crawl_notice_list(max_pages=3)
        print(f"找到 {len(notices)} 条公告")
        
        notices = notices[:max_notices]
        
        for i, notice in enumerate(notices, 1):
            print(f"\n处理公告 {i}/{len(notices)}: {notice.get('title', 'N/A')[:50]}...")
            
            # Step 2: extract -> raw_text
            html_or_text = notice.get('html_or_text', '')
            if not html_or_text:
                # 需要获取详情页
                detail = await crawler.crawl_notice_detail(notice)
                if not detail:
                    print(f"  跳过：无法获取详情")
                    continue
                html_or_text = detail.get('html_or_text', '')
                notice['url'] = detail.get('url', notice.get('url'))
            
            # 提取纯文本
            raw_text = crawler.extract_raw_text(html_or_text) if html_or_text else ''
            if not raw_text:
                print(f"  跳过：无法提取正文")
                continue
            
            # Step 3: hash 去重/更新
            content_hash = calculate_content_hash(raw_text)
            existing = None
            is_new = True
            
            if save_to_db:
                existing = get_notice_by_url(notice.get('url', ''))
                if existing:
                    # 检查内容是否更新
                    existing_hash = calculate_content_hash(existing.raw_text or '')
                    if existing_hash == content_hash:
                        print(f"  公告内容未变化，跳过")
                        continue
                    else:
                        print(f"  公告内容已更新，将重新分析")
                        is_new = False
            
            # Step 4: NEW/UPDATED -> analyze_notice(...) -> analysis_json
            analysis_json = None
            if analyze:
                try:
                    print(f"  进行 AI 分析...")
                    analysis = await analyze_notice(
                        title=notice.get('title', ''),
                        url=notice.get('url', ''),
                        raw_text=raw_text,
                        extracted_fields={}  # 可以进一步提取字段
                    )
                    analysis_json = analysis
                    print(f"  分析完成: {analysis.get('fit_label')} ({analysis.get('fit_score')}/100)")
                except Exception as e:
                    print(f"  AI 分析失败: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Step 5: 写入数据库
            if save_to_db:
                try:
                    save_notice(
                        title=notice.get('title', ''),
                        url=notice.get('url', ''),
                        raw_text=raw_text,
                        published_at=notice.get('published_at'),
                        analysis_json=analysis_json
                    )
                    print(f"  已保存到数据库 ({'新建' if is_new else '更新'})")
                except Exception as e:
                    print(f"  数据库保存失败: {e}")
                    import traceback
                    traceback.print_exc()
            
            results.append({
                'title': notice.get('title', ''),
                'url': notice.get('url', ''),
                'published_at': notice.get('published_at'),
                'raw_text': raw_text[:200] + '...' if len(raw_text) > 200 else raw_text,
                'analysis': analysis_json,
                'is_new': is_new
            })
    
    return results


if __name__ == "__main__":
    async def test():
        results = await crawl_and_analyze(max_notices=5, analyze=True, save_to_db=True)
        print(f"\n\n共处理 {len(results)} 条公告")
    
    asyncio.run(test())
