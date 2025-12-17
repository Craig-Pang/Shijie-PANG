"""
中国电建阳光采购网爬虫
Pipeline: crawler -> extract -> hash去重 -> NEW/UPDATED -> analyze -> 入库
支持 source_item_id 和 canonical_key
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
from ..db import save_notice, get_notice_by_canonical_key, init_db
from .powerchina_crawler_playwright import (
    fetch_html_with_playwright,
    fetch_notice_list_with_playwright,
    fetch_detail_with_playwright,
    PlaywrightFetcher
)


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
        # 统计信息
        self.stats = {
            'list_id_extracted': 0,
            'list_id_failed': 0,
            'detail_fetched': 0,
            'detail_failed': 0,
            'detail_fail_reasons': {}
        }
    
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
    
    def extract_source_item_id(self, row_element) -> Optional[str]:
        """
        从 DOM 元素中提取 source_item_id
        
        参数:
            row_element: BeautifulSoup 行元素
        
        返回:
            source_item_id 或 None
        """
        # 方法1: 查找 data-id 属性
        item_id = row_element.get('data-id') or row_element.get('data-item-id') or row_element.get('data-notice-id')
        if item_id:
            return str(item_id)
        
        # 方法2: 从 onclick 中提取
        onclick = row_element.get('onclick', '')
        if onclick:
            match = re.search(r"['\"](\d+)['\"]", onclick)
            if match:
                return match.group(1)
        
        # 方法3: 查找隐藏字段
        hidden_inputs = row_element.find_all('input', type='hidden')
        for input_elem in hidden_inputs:
            name = input_elem.get('name', '').lower()
            if 'id' in name:
                value = input_elem.get('value')
                if value:
                    return str(value)
        
        return None
    
    def generate_canonical_key(self, source_item_id: Optional[str], index: int, title: str) -> str:
        """
        生成 canonical_key
        
        参数:
            source_item_id: 源站项目ID
            index: 列表序号
            title: 标题
        
        返回:
            canonical_key
        """
        if source_item_id:
            return f"powerchina:{source_item_id}"
        else:
            # 使用列表序号 + 标题 hash
            title_hash = hashlib.md5(title.encode('utf-8')).hexdigest()[:8]
            return f"powerchina:index_{index}_hash_{title_hash}"
    
    async def fetch_page(self, url: str, use_fallback: bool = True) -> Optional[Tuple[str, str]]:
        """
        获取网页内容（带 fallback）
        """
        print(f"[FETCH_MODE=requests] 获取页面: {url}")
        html = await self._fetch_with_requests(url)
        
        if html and len(html) > 5000:
            print(f"[FETCH_MODE=requests] 成功获取 HTML ({len(html)} 字符)")
            return (html, url)
        
        if (not html or len(html) <= 5000) and use_fallback and self.use_playwright_fallback:
            print(f"[FETCH_MODE=requests] 获取失败或内容为空，fallback 到 Playwright")
            result = await fetch_html_with_playwright(url, headless=True, timeout=60000, retries=2, debug=True)
            if result:
                html, final_url = result
                if html and len(html) > 5000:
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
        """解析 API 响应数据，返回 [{title, url, source_item_id, canonical_key, published_at, html_or_text}]"""
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
        
        for idx, item in enumerate(items):
            source_item_id = str(item.get('id') or item.get('noticeId') or item.get('tenderId') or '')
            title = item.get('title') or item.get('noticeTitle') or item.get('name') or ''
            
            if not title:
                continue
            
            canonical_key = self.generate_canonical_key(source_item_id, idx, title)
            
            notice = {
                'title': title,
                'url': item.get('url') or item.get('link') or item.get('detailUrl') or '',
                'source_item_id': source_item_id if source_item_id else None,
                'canonical_key': canonical_key,
                'published_at': None,
                'html_or_text': item.get('content') or item.get('summary') or ''
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
            
            if not notice['url'] and source_item_id:
                notice['url'] = f"{self.BASE_URL}/consult/notice/{source_item_id}"
            
            notices.append(notice)
        
        return notices
    
    def parse_notice_list(self, html: str) -> List[Dict]:
        """
        解析招标公告列表页，返回 [{title, url, source_item_id, canonical_key, published_at, html_or_text}]
        """
        soup = BeautifulSoup(html, 'html.parser')
        notices = []
        
        # 查找包含公告的表格
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            if len(rows) < 1:
                continue
            
            table_text = table.get_text()
            has_date = bool(re.search(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', table_text))
            
            if has_date and len(rows) > 5:
                for idx, row in enumerate(rows):
                    cells = row.find_all(['td', 'th'])
                    if len(cells) < 2:
                        continue
                    
                    # 提取 source_item_id
                    source_item_id = self.extract_source_item_id(row)
                    if source_item_id:
                        self.stats['list_id_extracted'] += 1
                    else:
                        self.stats['list_id_failed'] += 1
                    
                    # 第一列通常是标题
                    title_cell = cells[0]
                    title_link = title_cell.find('a', href=True)
                    
                    if title_link:
                        title = title_link.get_text(strip=True)
                        href = title_link.get('href')
                        notice_url = urljoin(self.BASE_URL, href) if href else ''
                    else:
                        title = title_cell.get_text(strip=True)
                        notice_url = ''
                    
                    # 生成 canonical_key
                    canonical_key = self.generate_canonical_key(source_item_id, idx, title)
                    
                    # 第二列通常是日期
                    date_cell = cells[1]
                    date_text = date_cell.get_text(strip=True)
                    date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', date_text)
                    
                    published_at = None
                    if date_match:
                        date_str = date_match.group(1)
                        for fmt in ['%Y-%m-%d', '%Y/%m/%d']:
                            try:
                                published_at = datetime.strptime(date_str, fmt)
                                break
                            except:
                                continue
                    
                    if title and len(title) > 10 and ('项目' in title or '招标' in title or '采购' in title or '工程' in title):
                        notices.append({
                            'title': title,
                            'url': notice_url,
                            'source_item_id': source_item_id,
                            'canonical_key': canonical_key,
                            'published_at': published_at,
                            'html_or_text': ''
                        })
        
        return notices
    
    def extract_raw_text(self, html: str) -> str:
        """从 HTML 提取纯文本"""
        soup = BeautifulSoup(html, 'html.parser')
        
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
        爬取公告列表，返回 [{title, url, source_item_id, canonical_key, published_at, html_or_text}]
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
            # 使用 HTML 解析（带 fallback）
            print(f"[FETCH_MODE=requests] 尝试 HTML 解析列表页...")
            result = await self.fetch_page(self.NOTICE_LIST_URL, use_fallback=True)
            if result:
                html, _ = result
                notices = self.parse_notice_list(html)
                all_notices.extend(notices)
        
        return all_notices
    
    async def crawl_notice_detail(self, notice: Dict, row_index: int = None) -> Optional[Dict]:
        """
        爬取单个公告详情，返回 {title, url, source_item_id, canonical_key, published_at, html_or_text}
        
        参数:
            notice: 公告信息
            row_index: 行索引（用于点击，如果没有 source_item_id）
        """
        # 如果已有 html_or_text，直接使用
        if notice.get('html_or_text'):
            return {
                'title': notice.get('title', ''),
                'url': notice.get('url', ''),
                'source_item_id': notice.get('source_item_id'),
                'canonical_key': notice.get('canonical_key', ''),
                'published_at': notice.get('published_at'),
                'html_or_text': notice.get('html_or_text')
            }
        
        # 尝试获取详情
        source_item_id = notice.get('source_item_id')
        url = notice.get('url', '')
        
        # 优先尝试推导接口或直接 URL
        if url:
            result = await self.fetch_page(url, use_fallback=True)
            if result:
                html, final_url = result
                self.stats['detail_fetched'] += 1
                return {
                    'title': notice.get('title', ''),
                    'url': final_url,
                    'source_item_id': source_item_id,
                    'canonical_key': notice.get('canonical_key', ''),
                    'published_at': notice.get('published_at'),
                    'html_or_text': html
                }
        
        # 如果 URL 为空，使用详情获取器
        # 优先尝试通过 ID
        if source_item_id:
            print(f"[DETAIL_FETCHER] 尝试通过 ID 获取详情: {source_item_id}")
            detail = await fetch_detail_with_playwright(
                item_id=source_item_id,
                row_selector=None,
                list_url=self.NOTICE_LIST_URL,
                base_url=self.BASE_URL,
                headless=True,
                timeout=60000
            )
            
            if detail:
                self.stats['detail_fetched'] += 1
                return {
                    'title': notice.get('title', ''),
                    'url': '',
                    'source_item_id': source_item_id,
                    'canonical_key': notice.get('canonical_key', ''),
                    'published_at': notice.get('published_at'),
                    'html_or_text': detail
                }
        
        # 如果没有 source_item_id，尝试通过点击获取（使用行索引）
        if row_index is not None:
            print(f"[DETAIL_FETCHER] 尝试通过点击行 {row_index} 获取详情")
            row_selector = f'tr.el-table__row:nth-child({row_index + 1})'  # +1 因为 CSS 从 1 开始
            detail = await fetch_detail_with_playwright(
                item_id=None,
                row_selector=row_selector,
                list_url=self.NOTICE_LIST_URL,
                base_url=self.BASE_URL,
                headless=True,
                timeout=60000
            )
            
            if detail:
                self.stats['detail_fetched'] += 1
                return {
                    'title': notice.get('title', ''),
                    'url': '',
                    'source_item_id': source_item_id,
                    'canonical_key': notice.get('canonical_key', ''),
                    'published_at': notice.get('published_at'),
                    'html_or_text': detail
                }
        
        # 所有方法都失败
        self.stats['detail_failed'] += 1
        reason = "接口未捕获" if source_item_id else "无 source_item_id 且点击失败"
        self.stats['detail_fail_reasons'][reason] = self.stats['detail_fail_reasons'].get(reason, 0) + 1
        
        return None


def calculate_content_hash(raw_text: str) -> str:
    """计算内容 hash（用于去重）"""
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
    1. crawler 返回 [{title, url, source_item_id, canonical_key, published_at, html_or_text}]
    2. extract -> raw_text
    3. hash 去重/更新（使用 canonical_key）
    4. NEW/UPDATED -> analyze_notice(...) -> analysis_json
    5. 写入数据库
    """
    if save_to_db:
        init_db()
    
    results = []
    
    async with PowerChinaCrawler(delay=delay) as crawler:
        # Step 1: 爬取列表
        print(f"开始爬取招标公告列表...")
        notices = await crawler.crawl_notice_list(max_pages=3)
        print(f"找到 {len(notices)} 条公告")
        
        # 输出列表 ID 提取统计
        total_list = crawler.stats['list_id_extracted'] + crawler.stats['list_id_failed']
        if total_list > 0:
            success_rate = (crawler.stats['list_id_extracted'] / total_list) * 100
            print(f"[STATS] 列表 ID 提取: {crawler.stats['list_id_extracted']}/{total_list} ({success_rate:.1f}%)")
        
        notices = notices[:max_notices]
        
        for i, notice in enumerate(notices, 1):
            print(f"\n处理公告 {i}/{len(notices)}: {notice.get('title', 'N/A')[:50]}...")
            print(f"  canonical_key: {notice.get('canonical_key', 'N/A')}")
            print(f"  source_item_id: {notice.get('source_item_id', 'N/A')}")
            
            # Step 2: extract -> raw_text
            html_or_text = notice.get('html_or_text', '')
            if not html_or_text:
                # 传递行索引用于点击（如果没有 source_item_id）
                detail = await crawler.crawl_notice_detail(notice, row_index=i-1)
                if not detail:
                    print(f"  跳过：无法获取详情")
                    continue
                html_or_text = detail.get('html_or_text', '')
                notice.update(detail)
            
            raw_text = crawler.extract_raw_text(html_or_text) if html_or_text else ''
            if not raw_text:
                print(f"  跳过：无法提取正文")
                continue
            
            # Step 3: hash 去重/更新（使用 canonical_key）
            content_hash = calculate_content_hash(raw_text)
            canonical_key = notice.get('canonical_key', '')
            existing = None
            is_new = True
            
            if save_to_db and canonical_key:
                existing = get_notice_by_canonical_key(canonical_key)
                if existing:
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
                        extracted_fields={}
                    )
                    analysis_json = analysis
                    # 显示分析结果（支持新的决策状态）
                    decision_state = analysis.get('decision_state', analysis.get('fit_label', 'UNKNOWN'))
                    fit_score = analysis.get('fit_score')
                    fit_label = analysis.get('fit_label', 'UNKNOWN')
                    input_quality = analysis.get('_meta', {}).get('input_quality', 'UNKNOWN')
                    decision_source = analysis.get('_meta', {}).get('decision_source', 'UNKNOWN')
                    
                    score_str = f"{fit_score}/100" if fit_score is not None else "null"
                    print(f"  分析完成: {decision_state} ({score_str})")
                    print(f"    输入质量: {input_quality}, 决策来源: {decision_source}")
                except Exception as e:
                    print(f"  AI 分析失败: {e}")
            
            # Step 5: 写入数据库
            if save_to_db and canonical_key:
                try:
                    save_notice(
                        title=notice.get('title', ''),
                        canonical_key=canonical_key,
                        url=notice.get('url', ''),
                        source_item_id=notice.get('source_item_id'),
                        raw_text=raw_text,
                        published_at=notice.get('published_at'),
                        analysis_json=analysis_json
                    )
                    print(f"  已保存到数据库 ({'新建' if is_new else '更新'})")
                except Exception as e:
                    print(f"  数据库保存失败: {e}")
            
            results.append({
                'title': notice.get('title', ''),
                'url': notice.get('url', ''),
                'source_item_id': notice.get('source_item_id'),
                'canonical_key': canonical_key,
                'published_at': notice.get('published_at'),
                'raw_text': raw_text[:200] + '...' if len(raw_text) > 200 else raw_text,
                'analysis': analysis_json,
                'is_new': is_new
            })
        
        # 输出详情获取统计
        total_detail = crawler.stats['detail_fetched'] + crawler.stats['detail_failed']
        if total_detail > 0:
            success_rate = (crawler.stats['detail_fetched'] / total_detail) * 100
            print(f"\n[STATS] 详情获取: {crawler.stats['detail_fetched']}/{total_detail} ({success_rate:.1f}%)")
            if crawler.stats['detail_fail_reasons']:
                print(f"[STATS] 失败原因:")
                for reason, count in crawler.stats['detail_fail_reasons'].items():
                    print(f"  - {reason}: {count}")
    
    return results


if __name__ == "__main__":
    async def test():
        results = await crawl_and_analyze(max_notices=5, analyze=True, save_to_db=True)
        print(f"\n\n共处理 {len(results)} 条公告")
    
    asyncio.run(test())
