#!/usr/bin/env python3
"""调试爬虫 - 查看实际网站结构"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import aiohttp
from bs4 import BeautifulSoup


async def debug():
    """调试网站结构"""
    url = "https://bid.powerchina.cn/consult/notice"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    
    async with aiohttp.ClientSession(headers=headers) as session:
        print(f"正在访问: {url}")
        async with session.get(url) as response:
            print(f"状态码: {response.status}")
            
            if response.status == 200:
                html = await response.text()
                print(f"HTML 长度: {len(html)} 字符")
                
                # 保存 HTML 用于分析
                with open('debug_page.html', 'w', encoding='utf-8') as f:
                    f.write(html)
                print("HTML 已保存到 debug_page.html")
                
                # 解析并查找可能的列表结构
                soup = BeautifulSoup(html, 'html.parser')
                
                print("\n查找可能的列表元素:")
                print("-" * 60)
                
                # 查找表格
                tables = soup.find_all('table')
                print(f"找到 {len(tables)} 个表格")
                if tables:
                    for i, table in enumerate(tables[:3], 1):
                        print(f"\n表格 {i}:")
                        rows = table.find_all('tr')
                        print(f"  行数: {len(rows)}")
                        if rows:
                            print(f"  第一行内容: {rows[0].get_text()[:100]}")
                
                # 查找链接
                links = soup.find_all('a', href=True)
                print(f"\n找到 {len(links)} 个链接")
                notice_links = [l for l in links if 'notice' in l.get('href', '').lower() or 'tender' in l.get('href', '').lower()]
                print(f"可能的公告链接: {len(notice_links)}")
                if notice_links:
                    for i, link in enumerate(notice_links[:5], 1):
                        print(f"  {i}. {link.get_text(strip=True)[:50]} -> {link.get('href')[:80]}")
                
                # 查找包含日期的元素
                import re
                date_pattern = re.compile(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}')
                date_elements = soup.find_all(string=date_pattern)
                print(f"\n找到 {len(date_elements)} 个包含日期的文本")
                if date_elements:
                    for i, elem in enumerate(date_elements[:5], 1):
                        print(f"  {i}. {elem.strip()[:80]}")
                
            else:
                print(f"请求失败: {response.status}")
                print(await response.text()[:500])


if __name__ == "__main__":
    asyncio.run(debug())

