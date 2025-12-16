"""
中国电建阳光采购网爬虫
爬取 https://bid.powerchina.cn/consult/notice 的招标公告

注意：该网站是 SPA（单页应用），需要查找 API 接口或使用浏览器渲染
"""

import re
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime
from urllib.parse import urljoin, urlparse

from ..agent import analyze_notice


class PowerChinaCrawler:
    """中国电建阳光采购网爬虫"""
    
    BASE_URL = "https://bid.powerchina.cn"
    NOTICE_LIST_URL = "https://bid.powerchina.cn/consult/notice"
    
    # 尝试的 API 接口路径
    API_PATHS = [
        "/api/consult/notice/list",
        "/api/notice/list",
        "/api/tender/list",
        "/consult/api/notice/list",
    ]
    
    def __init__(self, delay: float = 1.0):
        """
        初始化爬虫
        
        参数:
            delay: 请求间隔（秒），避免请求过快
        """
        self.delay = delay
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
    
    async def fetch_page(self, url: str) -> Optional[str]:
        """
        获取网页内容
        
        参数:
            url: 目标 URL
        
        返回:
            HTML 内容，失败返回 None
        """
        if not self.session:
            raise RuntimeError("Session not initialized. Use 'async with' context manager.")
        
        try:
            await asyncio.sleep(self.delay)
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    print(f"请求失败: {url}, 状态码: {response.status}")
                    return None
        except Exception as e:
            print(f"获取页面失败 {url}: {e}")
            return None
    
    async def fetch_api(self, url: str, params: Dict = None) -> Optional[Dict]:
        """
        尝试调用 API 接口
        
        参数:
            url: API URL
            params: 请求参数
        
        返回:
            JSON 响应，失败返回 None
        """
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
                        # 尝试解析为 JSON
                        try:
                            import json
                            return json.loads(text)
                        except:
                            return None
                else:
                    return None
        except Exception as e:
            print(f"API 调用失败 {url}: {e}")
            return None
    
    async def find_api_endpoint(self) -> Optional[str]:
        """
        尝试查找实际的 API 接口
        
        返回:
            API URL 或 None
        """
        # 方法1: 尝试常见的 API 路径
        for api_path in self.API_PATHS:
            api_url = urljoin(self.BASE_URL, api_path)
            print(f"尝试 API: {api_url}")
            
            # 尝试不同的参数组合
            test_params = [
                {'page': 1, 'pageSize': 10},
                {'pageNo': 1, 'pageSize': 10},
                {'current': 1, 'size': 10},
            ]
            
            for params in test_params:
                result = await self.fetch_api(api_url, params)
                if result and isinstance(result, dict):
                    # 检查是否包含列表数据
                    if 'data' in result or 'list' in result or 'records' in result:
                        print(f"找到 API 接口: {api_url}")
                        return api_url
        
        # 方法2: 从主页面查找 API 调用
        html = await self.fetch_page(self.NOTICE_LIST_URL)
        if html:
            # 查找 JavaScript 中的 API 调用
            api_patterns = [
                r'["\']([^"\']*api[^"\']*notice[^"\']*)["\']',
                r'["\']([^"\']*api[^"\']*list[^"\']*)["\']',
                r'url:\s*["\']([^"\']*api[^"\']*)["\']',
            ]
            
            for pattern in api_patterns:
                matches = re.findall(pattern, html, re.I)
                for match in matches:
                    if match.startswith('http'):
                        api_url = match
                    else:
                        api_url = urljoin(self.BASE_URL, match)
                    
                    print(f"从页面找到可能的 API: {api_url}")
                    result = await self.fetch_api(api_url)
                    if result:
                        return api_url
        
        return None
    
    def parse_api_response(self, data: Dict) -> List[Dict]:
        """
        解析 API 响应数据
        
        参数:
            data: API 返回的 JSON 数据
        
        返回:
            公告列表
        """
        notices = []
        
        # 尝试不同的数据结构
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
            
            # 尝试提取常见字段
            notice['title'] = item.get('title') or item.get('noticeTitle') or item.get('name') or ''
            notice['url'] = item.get('url') or item.get('link') or item.get('detailUrl') or ''
            
            # 构建完整 URL
            if notice['url'] and not notice['url'].startswith('http'):
                notice['url'] = urljoin(self.BASE_URL, notice['url'])
            
            # 提取日期
            date_field = item.get('publishDate') or item.get('createTime') or item.get('date') or item.get('publishTime') or ''
            if date_field:
                notice['publish_date'] = str(date_field)[:10]  # 取前10个字符（日期部分）
            
            # 提取 ID（用于构建详情 URL）
            notice_id = item.get('id') or item.get('noticeId') or item.get('tenderId') or ''
            if notice_id and not notice['url']:
                # 尝试构建详情 URL
                notice['url'] = f"{self.BASE_URL}/consult/notice/{notice_id}"
            
            if notice.get('title'):
                notices.append(notice)
        
        return notices
    
    def parse_notice_list(self, html: str) -> List[Dict]:
        """
        解析招标公告列表页（传统 HTML 解析，用于非 SPA 页面）
        
        参数:
            html: 列表页 HTML
        
        返回:
            公告信息列表
        """
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
        """
        解析招标公告详情页
        
        参数:
            html: 详情页 HTML
            url: 公告 URL
        
        返回:
            提取的字段字典
        """
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
        full_text = result['raw_text'].lower()
        
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
        """
        爬取公告列表
        
        参数:
            max_pages: 最大爬取页数
        
        返回:
            公告列表
        """
        all_notices = []
        
        # 首先尝试查找 API 接口
        print("尝试查找 API 接口...")
        api_url = await self.find_api_endpoint()
        
        if api_url:
            # 使用 API 接口
            print(f"使用 API 接口: {api_url}")
            for page in range(1, max_pages + 1):
                params_list = [
                    {'page': page, 'pageSize': 20},
                    {'pageNo': page, 'pageSize': 20},
                    {'current': page, 'size': 20},
                ]
                
                for params in params_list:
                    data = await self.fetch_api(api_url, params)
                    if data:
                        notices = self.parse_api_response(data)
                        if notices:
                            all_notices.extend(notices)
                            break
                
                if not notices:
                    break  # 没有更多数据
        else:
            # 回退到 HTML 解析
            print("未找到 API 接口，尝试 HTML 解析...")
            html = await self.fetch_page(self.NOTICE_LIST_URL)
            if html:
                notices = self.parse_notice_list(html)
                all_notices.extend(notices)
        
        return all_notices
    
    async def crawl_notice_detail(self, notice: Dict) -> Optional[Dict]:
        """
        爬取单个公告详情
        
        参数:
            notice: 公告基本信息（包含 url）
        
        返回:
            完整的公告数据
        """
        url = notice.get('url')
        if not url:
            return None
        
        html = await self.fetch_page(url)
        if not html:
            return None
        
        detail = self.parse_notice_detail(html, url)
        detail['title'] = detail.get('title') or notice.get('title', '')
        detail['publish_date'] = notice.get('publish_date')
        
        return detail


async def crawl_and_analyze(
    max_notices: int = 10,
    analyze: bool = True,
    delay: float = 1.0
) -> List[Dict]:
    """
    爬取并分析招标公告
    
    参数:
        max_notices: 最大爬取数量
        analyze: 是否使用 AI agent 分析
        delay: 请求延迟（秒）
    
    返回:
        包含分析和原始数据的列表
    """
    results = []
    
    async with PowerChinaCrawler(delay=delay) as crawler:
        print(f"开始爬取招标公告列表...")
        notices = await crawler.crawl_notice_list(max_pages=3)
        print(f"找到 {len(notices)} 条公告")
        
        notices = notices[:max_notices]
        
        for i, notice in enumerate(notices, 1):
            print(f"\n处理公告 {i}/{len(notices)}: {notice.get('title', 'N/A')[:50]}...")
            
            detail = await crawler.crawl_notice_detail(notice)
            if not detail:
                print(f"  跳过：无法获取详情")
                continue
            
            if analyze:
                try:
                    print(f"  进行 AI 分析...")
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
                    detail['analysis'] = None
            
            results.append(detail)
    
    return results


if __name__ == "__main__":
    async def test():
        results = await crawl_and_analyze(max_notices=5, analyze=True)
        print(f"\n\n共处理 {len(results)} 条公告")
        for result in results:
            print(f"\n标题: {result.get('title')}")
            if result.get('analysis'):
                analysis = result['analysis']
                print(f"  评分: {analysis.get('fit_score')}/100")
                print(f"  标签: {analysis.get('fit_label')}")
    
    asyncio.run(test())
