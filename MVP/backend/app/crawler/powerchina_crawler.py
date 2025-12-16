"""
中国电建阳光采购网爬虫
爬取 https://bid.powerchina.cn/consult/notice 的招标公告
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
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
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
            await asyncio.sleep(self.delay)  # 延迟避免请求过快
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    print(f"请求失败: {url}, 状态码: {response.status}")
                    return None
        except Exception as e:
            print(f"获取页面失败 {url}: {e}")
            return None
    
    def parse_notice_list(self, html: str) -> List[Dict]:
        """
        解析招标公告列表页
        
        参数:
            html: 列表页 HTML
        
        返回:
            公告信息列表，每个包含 title, url, publish_date 等
        """
        soup = BeautifulSoup(html, 'html.parser')
        notices = []
        
        # 尝试多种可能的列表结构
        # 方法1: 查找表格行
        table_rows = soup.find_all('tr')
        for row in table_rows:
            links = row.find_all('a', href=True)
            if not links:
                continue
            
            notice = {}
            # 提取标题和链接
            title_link = links[0]
            notice['title'] = title_link.get_text(strip=True)
            notice['url'] = urljoin(self.BASE_URL, title_link['href'])
            
            # 提取日期（通常在表格的某一列）
            date_cells = row.find_all('td')
            for cell in date_cells:
                text = cell.get_text(strip=True)
                # 匹配日期格式：2024-01-01 或 2024/01/01
                date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', text)
                if date_match:
                    notice['publish_date'] = date_match.group(1)
                    break
            
            if notice.get('title') and notice.get('url'):
                notices.append(notice)
        
        # 方法2: 如果表格方法没找到，尝试查找列表项
        if not notices:
            list_items = soup.find_all(['li', 'div'], class_=re.compile(r'notice|item|list', re.I))
            for item in list_items:
                link = item.find('a', href=True)
                if not link:
                    continue
                
                notice = {
                    'title': link.get_text(strip=True),
                    'url': urljoin(self.BASE_URL, link['href'])
                }
                
                # 查找日期
                date_elem = item.find(string=re.compile(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}'))
                if date_elem:
                    notice['publish_date'] = date_elem.strip()
                
                if notice.get('title'):
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
            # 尝试查找所有段落
            content_elem = soup.find('body')
        
        if content_elem:
            # 移除脚本和样式
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
                extracted['qualification'] = match.group(1).strip()[:200]  # 限制长度
                break
        
        # 提取项目范围/内容
        scope_patterns = [
            r'项目内容[：:]\s*([^\n]+(?:\n[^\n]+){0,5})',
            r'建设内容[：:]\s*([^\n]+(?:\n[^\n]+){0,5})',
            r'工程内容[：:]\s*([^\n]+(?:\n[^\n]+){0,5})',
        ]
        for pattern in scope_patterns:
            match = re.search(pattern, result['raw_text'], re.I)
            if match:
                extracted['scope'] = match.group(1).strip()[:500]  # 限制长度
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
        
        # 先爬取第一页
        html = await self.fetch_page(self.NOTICE_LIST_URL)
        if not html:
            print("无法获取列表页")
            return []
        
        notices = self.parse_notice_list(html)
        all_notices.extend(notices)
        
        # 尝试爬取更多页（如果网站支持分页）
        # 这里需要根据实际网站的分页结构调整
        for page in range(2, max_pages + 1):
            # 尝试不同的分页 URL 格式
            page_urls = [
                f"{self.NOTICE_LIST_URL}?page={page}",
                f"{self.NOTICE_LIST_URL}?p={page}",
                f"{self.NOTICE_LIST_URL}/page/{page}",
            ]
            
            found = False
            for page_url in page_urls:
                html = await self.fetch_page(page_url)
                if html:
                    notices = self.parse_notice_list(html)
                    if notices:
                        all_notices.extend(notices)
                        found = True
                        break
            
            if not found:
                break  # 没有更多页面
        
        return all_notices
    
    async def crawl_notice_detail(self, notice: Dict) -> Optional[Dict]:
        """
        爬取单个公告详情
        
        参数:
            notice: 公告基本信息（包含 url）
        
        返回:
            完整的公告数据（包含详情和提取字段）
        """
        url = notice.get('url')
        if not url:
            return None
        
        html = await self.fetch_page(url)
        if not html:
            return None
        
        detail = self.parse_notice_detail(html, url)
        
        # 合并基本信息
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
        # 1. 爬取列表
        print(f"开始爬取招标公告列表...")
        notices = await crawler.crawl_notice_list(max_pages=3)
        print(f"找到 {len(notices)} 条公告")
        
        # 2. 限制数量
        notices = notices[:max_notices]
        
        # 3. 爬取详情并分析
        for i, notice in enumerate(notices, 1):
            print(f"\n处理公告 {i}/{len(notices)}: {notice.get('title', 'N/A')[:50]}...")
            
            # 爬取详情
            detail = await crawler.crawl_notice_detail(notice)
            if not detail:
                print(f"  跳过：无法获取详情")
                continue
            
            # AI 分析
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
    # 测试代码
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

