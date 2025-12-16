#!/bin/bash
# Ollama 安装和运行脚本

echo "=========================================="
echo "Ollama 安装和运行指南"
echo "=========================================="

# 检查是否已安装
if command -v ollama &> /dev/null; then
    echo "✅ Ollama 已安装"
    ollama --version
else
    echo "❌ Ollama 未安装"
    echo ""
    echo "安装方法："
    echo ""
    echo "方法 1: 使用 Homebrew（推荐）"
    echo "  brew install ollama"
    echo ""
    echo "方法 2: 从官网下载"
    echo "  访问: https://ollama.com/download"
    echo "  下载 macOS 安装包并安装"
    echo ""
    echo "安装完成后，运行以下命令启动服务："
    echo "  ollama serve"
    echo ""
    exit 1
fi

echo ""
echo "=========================================="
echo "启动 Ollama 服务"
echo "=========================================="

# 检查服务是否运行
if curl -s http://localhost:11434 > /dev/null 2>&1; then
    echo "✅ Ollama 服务已在运行"
    echo "访问: http://localhost:11434"
else
    echo "启动 Ollama 服务..."
    echo "运行命令: ollama serve"
    echo ""
    echo "或者运行: nohup ollama serve > ollama.log 2>&1 &"
    echo ""
    echo "服务启动后，访问: http://localhost:11434"
fi

echo ""
echo "=========================================="
echo "下载模型（如果需要）"
echo "=========================================="
echo "项目使用的默认模型: qwen2.5:0.5b"
echo ""
echo "下载模型命令:"
echo "  ollama pull qwen2.5:0.5b"
echo ""
echo "或者使用其他模型:"
echo "  ollama pull qwen2.5:1.5b"
echo "  ollama pull qwen2.5:3b"
echo "  ollama pull llama3.2"
echo ""

