"""
Ollama API 客户端
调用本地 Ollama 服务
"""

import os
import json
import aiohttp
from typing import Dict, Optional


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")


async def call_ollama(prompt: str, model: str = None) -> str:
    """
    调用 Ollama API
    
    参数:
        prompt: 输入 prompt
        model: 模型名称（默认从环境变量读取）
    
    返回:
        模型输出的文本
    """
    if model is None:
        model = OLLAMA_MODEL
    
    url = f"{OLLAMA_BASE_URL}/api/generate"
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json"  # 强制 JSON 输出
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Ollama API 错误: {response.status}, {error_text}")
                
                result = await response.json()
                return result.get("response", "")
    except aiohttp.ClientError as e:
        raise Exception(f"Ollama 连接错误: {str(e)}")
    except Exception as e:
        raise Exception(f"Ollama 调用失败: {str(e)}")


def parse_json_response(response_text: str) -> Optional[Dict]:
    """
    解析 JSON 响应
    
    参数:
        response_text: 模型输出的文本
    
    返回:
        解析后的字典，如果解析失败返回 None
    """
    if not response_text:
        return None
    
    # 尝试直接解析
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass
    
    # 尝试提取 JSON 块（如果被其他文本包裹）
    # 查找第一个 { 和最后一个 }
    start_idx = response_text.find('{')
    end_idx = response_text.rfind('}')
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        json_str = response_text[start_idx:end_idx + 1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
    
    # 如果都失败，返回 None
    return None

