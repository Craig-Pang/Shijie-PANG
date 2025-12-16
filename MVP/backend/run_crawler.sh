#!/bin/bash
# 爬虫运行脚本

cd "$(dirname "$0")"

echo "检查依赖..."
python3 -c "import aiohttp, bs4, pydantic" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "正在安装依赖..."
    python3 -m pip install --user aiohttp beautifulsoup4 pydantic lxml
fi

echo "运行爬虫..."
python3 test_crawler.py

