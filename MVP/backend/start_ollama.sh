#!/bin/bash
# 启动 Ollama 服务脚本

echo "启动 Ollama 服务..."

# 检查是否已运行
if curl -s http://localhost:11434 > /dev/null 2>&1; then
    echo "✅ Ollama 服务已在运行"
    echo "访问: http://localhost:11434"
    exit 0
fi

# 启动服务（后台运行）
nohup ollama serve > ollama.log 2>&1 &
OLLAMA_PID=$!
echo $OLLAMA_PID > ollama.pid

echo "Ollama 服务正在启动 (PID: $OLLAMA_PID)..."
echo "日志文件: ollama.log"
echo "PID 文件: ollama.pid"

# 等待服务启动
for i in {1..10}; do
    sleep 1
    if curl -s http://localhost:11434 > /dev/null 2>&1; then
        echo "✅ Ollama 服务已启动"
        echo "访问: http://localhost:11434"
        echo ""
        echo "停止服务: kill \$(cat ollama.pid)"
        exit 0
    fi
    echo -n "."
done

echo ""
echo "⚠️  服务启动可能较慢，请稍后检查: curl http://localhost:11434"
echo "查看日志: tail -f ollama.log"

