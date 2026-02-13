# Ollama Chat Client 一键包

## 简介

Ollama Chat Client 是一个基于本地 Ollama 服务的聊天客户端，支持通过 API 方式调用，并且已经适配阿里 API 调用规范，确保通用性。

## 功能特性

- ✅ 本地 Ollama 模型聊天
- ✅ API 服务端，支持远程调用
- ✅ 阿里 API 调用规范兼容
- ✅ 一键启动，自动安装依赖
- ✅ 配置文件管理
- ✅ API Key 管理


## 快速开始

### 1. 环境要求

- Python 3.8 或更高版本
- （可选）本地已安装并运行 Ollama 服务

### 2. 启动方式

**方法一：使用启动脚本（推荐）**

直接运行 `start.py` 启动脚本，它会自动检查环境并安装依赖：


```bash
python start.py
```

**方法二：手动启动**

1. 安装依赖

```bash
pip install -r requirements.txt
```

2. 启动应用

```bash
python main.py
```

## API 服务使用

### 1. 启用 API 服务

1. 运行应用后，在侧边栏的 "API服务管理" 区域
2. 打开 "启用API服务" 开关
3. 设置服务端口（默认为 5000）
4. 点击 "生成新API Key" 按钮获取 API 密钥

### 2. API 调用方式

#### 阿里 API 调用方式（推荐）

**请求示例：**

```bash
# POST 请求
curl -X POST "http://localhost:5000/api/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "AccessKeyId": "your-api-key",
    "Message": "你好",
    "Model": "llama2"
  }'
```

**响应示例：**

```json
{
  "code": 200,
  "message": "Success",
  "data": {
    "response": "你好！我是一个基于 Ollama 的 AI 助手，有什么我可以帮助你的吗？"
  }
}
```

#### 标准 REST API 方式

**请求示例：**

```bash
# POST 请求
curl -X POST "http://localhost:5000/api/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-api-key" \
  -d '{
    "message": "你好",
    "model": "llama2"
  }'
```

**响应示例：**

```json
{
  "code": 200,
  "message": "Success",
  "data": {
    "response": "你好！我是一个基于 Ollama 的 AI 助手，有什么我可以帮助你的吗？"
  }
}
```

### 3. API 端点

- **POST /api/chat**：聊天请求
  - 参数：
    - `message` 或 `Message`：聊天消息内容（必填）
    - `model` 或 `Model`：模型名称（可选，默认使用当前设置的模型）
    - `AccessKeyId`：API 密钥（阿里 API 方式）
  - 或使用标准 `Authorization: Bearer` 头部传递 API 密钥

- **GET /api/models**：获取可用模型列表
  - 响应：返回可用的模型列表

## 配置管理

应用使用 `config.ini` 文件管理配置，主要配置项包括：

```ini
[App]
# 应用配置
app_name = Ollama Chat Client
app_version = 1.0.0

[Server]
# API服务配置
enable_api_server = false
api_server_port = 5000

[Ollama]
# Ollama配置
base_url = http://localhost:11434
default_model = llama2

[API]
# API配置
enable_external_api = false
external_api_base_url = https://api.openai.com/v1
```

## 常见问题

### 1. 启动失败，提示缺少依赖

启动脚本会自动安装依赖，如果手动启动失败，请运行：

```bash
pip install -r requirements.txt
```

### 2. 无法连接到 Ollama

请确保：
- Ollama 服务已安装并正在运行
- 配置文件中的 `base_url` 设置正确（默认为 `http://localhost:11434`）

### 3. API 调用返回 401 错误

请检查：
- API Key 是否正确
- API Key 是否已过期
- API Key 的传递方式是否正确

## 开发说明

### 项目结构

```
.
├── main.py            # 主应用文件
├── start.py           # 启动脚本
├── config.ini         # 配置文件
├── requirements.txt   # 依赖列表
└── README.md          # 说明文档
```

### 打包为可执行文件

可以使用 PyInstaller 将应用打包为可执行文件：

```bash
pip install pyinstaller
pyinstaller --onefile --windowed main.py
```

## 许可证

本项目采用 MIT 许可证。






