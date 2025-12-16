#!/bin/bash
# 设置虚拟环境并运行爬虫

cd "$(dirname "$0")"

echo "创建虚拟环境..."
python3 -m venv venv

echo "激活虚拟环境..."
source venv/bin/activate

echo "安装依赖..."
pip install -q aiohttp beautifulsoup4 pydantic lxml

echo "运行爬虫测试..."
python3 test_crawler.py

deactivate

