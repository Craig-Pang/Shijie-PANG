# Ollama 使用指南

## 安装 Ollama

### macOS 安装

**方法 1: 使用 Homebrew（推荐）**
```bash
brew install ollama
```

**方法 2: 从官网下载**
访问 https://ollama.com/download 下载 macOS 安装包

## 启动 Ollama 服务

### 方法 1: 使用启动脚本（推荐）
```bash
cd MVP/backend
./start_ollama.sh
```

### 方法 2: 手动启动
```bash
# 前台运行（会占用终端）
ollama serve

# 后台运行
nohup ollama serve > ollama.log 2>&1 &
```

### 方法 3: 使用 launchd（macOS 开机自启）
```bash
# 创建 plist 文件
cat > ~/Library/LaunchAgents/com.ollama.ollama.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ollama.ollama</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/ollama</string>
        <string>serve</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
EOF

# 加载服务
launchctl load ~/Library/LaunchAgents/com.ollama.ollama.plist
```

## 下载模型

项目默认使用 `qwen2.5:0.5b` 模型（约 300MB，速度快）：

```bash
ollama pull qwen2.5:0.5b
```

### 其他可用模型

如果需要更好的效果，可以使用更大的模型：

```bash
# 1.5B 参数（约 1GB）
ollama pull qwen2.5:1.5b

# 3B 参数（约 2GB）
ollama pull qwen2.5:3b

# 7B 参数（约 4.5GB，效果最好但较慢）
ollama pull qwen2.5:7b
```

### 查看已安装的模型
```bash
ollama list
```

## 验证安装

### 检查服务状态
```bash
curl http://localhost:11434
```

应该返回：`Ollama is running`

### 测试模型
```bash
ollama run qwen2.5:0.5b "你好"
```

## 配置环境变量（可选）

如果需要使用不同的模型或服务地址，可以设置环境变量：

```bash
# 使用不同的模型
export OLLAMA_MODEL=qwen2.5:1.5b

# 使用不同的服务地址
export OLLAMA_BASE_URL=http://localhost:11434
```

## 停止服务

```bash
# 如果使用启动脚本
kill $(cat ollama.pid)

# 或者查找进程并停止
pkill ollama

# 如果使用 launchd
launchctl unload ~/Library/LaunchAgents/com.ollama.ollama.plist
```

## 查看日志

```bash
# 如果使用启动脚本
tail -f ollama.log

# 或者查看系统日志（如果使用 launchd）
log show --predicate 'process == "ollama"' --last 1h
```

## 常见问题

### 1. 端口被占用
如果 11434 端口被占用，可以修改端口：
```bash
OLLAMA_HOST=0.0.0.0:11435 ollama serve
```

### 2. 模型下载慢
可以设置镜像源（如果可用）：
```bash
export OLLAMA_HOST=https://ollama.com
```

### 3. 内存不足
使用较小的模型（如 qwen2.5:0.5b）或增加系统内存。

## 在项目中使用

安装并启动 Ollama 后，爬虫会自动使用它进行 AI 分析：

```bash
cd MVP/backend
source venv/bin/activate
PYTHONPATH=/Users/pangshijie/Documents/AIManagement/MVP/backend python3 -m app.crawler.main --max-notices 5
```

AI 分析会自动调用 Ollama 服务。

