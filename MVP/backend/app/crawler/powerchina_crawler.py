"""
中国电建阳光采购网爬虫
支持自动 fallback 到 Playwright
"""

import re
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime
from urllib.parse import urljoin

from ..agent import analyze_notice
from ..db import save_notice, get_notice_by_url, init_db
from .powerchina_crawler_playwright import fetch_with_playwright


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
    
    async def fetch_page(self, url: str, use_fallback: bool = True) -> Optional[str]:
        """
        获取网页内容（带 fallback）
        
        参数:
            url: 目标 URL
            use_fallback: 是否在失败时使用 Playwright fallback
        
        返回:
            HTML 内容
        """
        # 首先尝试 requests 方式
        print(f"[FETCH_MODE=requests] 获取页面: {url}")
        html = await self._fetch_with_requests(url)
        
        # 检查内容是否有效
        if html and len(html) > 1000:
            print(f"[FETCH_MODE=requests] 成功获取 HTML ({len(html)} 字符)")
            return html
        
        # 如果失败且启用 fallback，使用 Playwright
        if (not html or len(html) <= 1000) and use_fallback and self.use_playwright_fallback:
            print(f"[FETCH_MODE=requests] 获取失败或内容为空，fallback 到 Playwright")
            html = await fetch_with_playwright(url, headless=True, timeout=30000, retries=3)
            if html and len(html) > 1000:
                return html
        
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
        """解析 API 响应数据"""
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
            notice = {}
            notice['title'] = item.get('title') or item.get('noticeTitle') or item.get('name') or ''
            notice['url'] = item.get('url') or item.get('link') or item.get('detailUrl') or ''
            
            if notice['url'] and not notice['url'].startswith('http'):
                notice['url'] = urljoin(self.BASE_URL, notice['url'])
            
            date_field = item.get('publishDate') or item.get('createTime') or item.get('date') or item.get('publishTime') or ''
            if date_field:
                notice['publish_date'] = str(date_field)[:10]
            
            notice_id = item.get('id') or item.get('noticeId') or item.get('tenderId') or ''
            if notice_id and not notice['url']:
                notice['url'] = f"{self.BASE_URL}/consult/notice/{notice_id}"
            
            if notice.get('title'):
                notices.append(notice)
        
        return notices
    
    def parse_notice_list(self, html: str) -> List[Dict]:
        """解析招标公告列表页"""
        soup = BeautifulSoup(html, 'html.parser')
        notices = []
        
        # 查找表格行
        table_rows = soup.find_all('tr')
        for row in table_rows:
            links = row.find_all('a', href=True)
            if not links:
                continue
            
            notice = {}
            title_link = links[0]
            notice['title'] = title_link.get_text(strip=True)
            notice['url'] = urljoin(self.BASE_URL, title_link['href'])
            
            # 提取日期
            date_cells = row.find_all('td')
            for cell in date_cells:
                text = cell.get_text(strip=True)
                date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', text)
                if date_match:
                    notice['publish_date'] = date_match.group(1)
                    break
            
            if notice.get('title') and notice.get('url'):
                notices.append(notice)
        
        return notices
    
    def parse_notice_detail(self, html: str, url: str) -> Dict:
        """解析招标公告详情页"""
        soup = BeautifulSoup(html, 'html.parser')
        result = {
            'url': url,
            'title': '',
            'raw_text': '',
            'extracted_fields': {}
        }
        
        # 提取标题
        title_elem = soup.find(['h1', 'h2', 'h3'], class_=re.compile(r'title|head', re.I))
        if not title_elem:
            title_elem = soup.find('title')
        if title_elem:
            result['title'] = title_elem.get_text(strip=True)
        
        # 提取正文内容
        content_elem = soup.find(['div', 'article', 'section'], class_=re.compile(r'content|detail|main|body', re.I))
        if not content_elem:
            content_elem = soup.find('body')
        
        if content_elem:
            for script in content_elem(["script", "style", "nav", "header", "footer"]):
                script.decompose()
            result['raw_text'] = content_elem.get_text(separator='\n', strip=True)
        
        # 提取关键字段
        extracted = {}
        
        # 提取地点
        location_patterns = [
            r'项目地点[：:]\s*([^\n]+)',
            r'建设地点[：:]\s*([^\n]+)',
            r'地点[：:]\s*([^\n]+)',
            r'位于\s*([^\n]+)',
        ]
        for pattern in location_patterns:
            match = re.search(pattern, result['raw_text'], re.I)
            if match:
                extracted['location'] = match.group(1).strip()
                break
        
        # 提取吨位
        tonnage_patterns = [
            r'(\d+(?:\.\d+)?)\s*[吨tT]',
            r'约\s*(\d+(?:\.\d+)?)\s*[吨tT]',
            r'钢结构.*?(\d+(?:\.\d+)?)\s*[吨tT]',
            r'(\d+(?:\.\d+)?)\s*吨位',
        ]
        for pattern in tonnage_patterns:
            match = re.search(pattern, result['raw_text'], re.I)
            if match:
                extracted['tonnage'] = match.group(1) + '吨'
                break
        
        # 提取截止时间
        deadline_patterns = [
            r'投标截止[时间]?[：:]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2}\s*\d{1,2}:\d{2})',
            r'截止时间[：:]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2}\s*\d{1,2}:\d{2})',
            r'报名截止[：:]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})',
            r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})\s*[前之前]',
        ]
        for pattern in deadline_patterns:
            match = re.search(pattern, result['raw_text'], re.I)
            if match:
                extracted['deadline'] = match.group(1).strip()
                break
        
        # 提取资质要求
        qual_patterns = [
            r'资质要求[：:]\s*([^\n]+(?:\n[^\n]+){0,3})',
            r'资质[：:]\s*([^\n]+(?:\n[^\n]+){0,2})',
            r'专业承包[：:]\s*([^\n]+)',
        ]
        for pattern in qual_patterns:
            match = re.search(pattern, result['raw_text'], re.I)
            if match:
                extracted['qualification'] = match.group(1).strip()[:200]
                break
        
        # 提取项目范围
        scope_patterns = [
            r'项目内容[：:]\s*([^\n]+(?:\n[^\n]+){0,5})',
            r'建设内容[：:]\s*([^\n]+(?:\n[^\n]+){0,5})',
            r'工程内容[：:]\s*([^\n]+(?:\n[^\n]+){0,5})',
        ]
        for pattern in scope_patterns:
            match = re.search(pattern, result['raw_text'], re.I)
            if match:
                extracted['scope'] = match.group(1).strip()[:500]
                break
        
        result['extracted_fields'] = extracted
        return result
    
    async def crawl_notice_list(self, max_pages: int = 5) -> List[Dict]:
        """爬取公告列表"""
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
            # 使用 HTML 解析（带 fallback）
            print(f"[FETCH_MODE=requests] 尝试 HTML 解析列表页...")
            html = await self.fetch_page(self.NOTICE_LIST_URL, use_fallback=True)
            if html:
                notices = self.parse_notice_list(html)
                all_notices.extend(notices)
        
        return all_notices
    
    async def crawl_notice_detail(self, notice: Dict) -> Optional[Dict]:
        """爬取单个公告详情（带 fallback）"""
        url = notice.get('url')
        if not url:
            return None
        
        html = await self.fetch_page(url, use_fallback=True)
        if not html:
            return None
        
        detail = self.parse_notice_detail(html, url)
        detail['title'] = detail.get('title') or notice.get('title', '')
        detail['publish_date'] = notice.get('publish_date')
        
        return detail


async def crawl_and_analyze(
    max_notices: int = 10,
    analyze: bool = True,
    delay: float = 1.0,
    save_to_db: bool = True
) -> List[Dict]:
    """
    爬取并分析招标公告，自动保存到数据库
    
    参数:
        max_notices: 最大爬取数量
        analyze: 是否使用 AI agent 分析
        delay: 请求延迟（秒）
        save_to_db: 是否保存到数据库
    
    返回:
        包含分析和原始数据的列表
    """
    # 初始化数据库
    if save_to_db:
        init_db()
    
    results = []
    
    async with PowerChinaCrawler(delay=delay) as crawler:
        print(f"开始爬取招标公告列表...")
        notices = await crawler.crawl_notice_list(max_pages=3)
        print(f"找到 {len(notices)} 条公告")
        
        notices = notices[:max_notices]
        
        for i, notice in enumerate(notices, 1):
            print(f"\n处理公告 {i}/{len(notices)}: {notice.get('title', 'N/A')[:50]}...")
            
            # 检查是否已存在
            if save_to_db:
                existing = get_notice_by_url(notice.get('url', ''))
                if existing and existing.raw_text:
                    print(f"  公告已存在，跳过")
                    continue
            
            # 爬取详情
            detail = await crawler.crawl_notice_detail(notice)
            if not detail or not detail.get('raw_text'):
                print(f"  跳过：无法获取详情或正文为空")
                continue
            
            # 解析发布日期
            published_at = None
            if detail.get('publish_date'):
                try:
                    # 尝试解析日期
                    date_str = detail['publish_date']
                    for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%Y-%m-%d %H:%M:%S']:
                        try:
                            published_at = datetime.strptime(date_str[:10], fmt[:10])
                            break
                        except:
                            continue
                except:
                    pass
            
            # AI 分析
            analysis_json = None
            if analyze:
                try:
                    print(f"  进行 AI 分析...")
                    analysis = await analyze_notice(
                        title=detail.get('title', ''),
                        url=detail.get('url', ''),
                        raw_text=detail.get('raw_text', ''),
                        extracted_fields=detail.get('extracted_fields', {})
                    )
                    analysis_json = analysis
                    detail['analysis'] = analysis
                    print(f"  分析完成: {analysis.get('fit_label')} ({analysis.get('fit_score')}/100)")
                except Exception as e:
                    print(f"  AI 分析失败: {e}")
                    detail['analysis'] = None
            
            # 保存到数据库
            if save_to_db:
                try:
                    save_notice(
                        title=detail.get('title', ''),
                        url=detail.get('url', ''),
                        raw_text=detail.get('raw_text', ''),
                        published_at=published_at,
                        analysis_json=analysis_json
                    )
                    print(f"  已保存到数据库")
                except Exception as e:
                    print(f"  数据库保存失败: {e}")
            
            results.append(detail)
    
    return results


if __name__ == "__main__":
    async def test():
        results = await crawl_and_analyze(max_notices=5, analyze=True, save_to_db=True)
        print(f"\n\n共处理 {len(results)} 条公告")
    
    asyncio.run(test())
