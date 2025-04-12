# SmartInfo 智能信息系统

一个基于FastAPI和Tauri+React的智能信息聚合和问答系统。

## 项目结构

```
SmartInfo/
├── src/                    # 后端代码（Python FastAPI）
│   ├── api/                # API定义
│   │   ├── routers/        # REST API路由
│   │   ├── schemas/        # API数据模型
│   │   └── websockets/     # WebSocket端点
│   ├── services/           # 业务服务
│   └── main.py             # 主程序入口
│
└── frontend-react-tauri/   # 前端代码（Tauri + React + TypeScript）
    ├── src/                # 前端源代码
    │   ├── components/     # 共享组件
    │   ├── hooks/          # 自定义Hooks
    │   ├── services/       # API服务
    │   ├── store/          # 状态管理
    │   ├── types/          # 类型定义
    │   ├── views/          # 页面视图
    │   ├── App.tsx         # 主应用组件
    │   └── main.tsx        # 入口文件
    ├── src-tauri/          # Tauri配置和原生代码
    └── package.json        # 项目依赖
```

## 运行方法

### 1. 运行后端（FastAPI）

确保已安装Python 3.12或更高版本，以及所需依赖：

```bash
cd src
pip install -r requirements.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

后端将在 http://127.0.0.1:8000 上运行。

### 2. 运行前端（Tauri + React）

确保已安装Node.js、npm和Rust环境：

```bash
cd frontend-react-tauri
npm install
npm run tauri dev
```

## 开发须知

1. **后端API变更**：在`backend/api`目录下进行
2. **前端类型定义**：需要与后端API保持同步，位于`frontend/src/types`
3. **前端API服务**：位于`frontend/src/services/api.ts`，需要与后端路由保持一致
4. **WebSocket服务**：前端连接后端WebSocket的客户端实现位于`frontend/src/services/websocket.ts`

## 功能概述

1. **新闻聚合**：自动抓取、分析、存储和展示新闻内容
2. **智能问答**：基于已收集的信息提供问答功能
3. **系统设置**：管理API密钥和系统配置

## 功能

- 新闻采集和分析
- 问答交互
- 设置管理

## 安装

1. 克隆仓库：

```bash
git clone https://github.com/yourusername/SmartInfo.git
cd SmartInfo
```

2. 安装依赖项：

```bash
pip install -r requirements.txt
```

## 运行服务器

```bash
python -m backend.main
```

默认情况下，服务器将在 `http://127.0.0.1:8000` 运行。

### 命令行参数

- `--host`: 指定主机地址（默认：127.0.0.1）
- `--port`: 指定端口号（默认：8000）
- `--reset-sources`: 重置新闻源为默认值
- `--clear-news`: 清除所有新闻数据
- `--reset-database`: 重置整个数据库
- `--log-level`: 设置日志级别（DEBUG、INFO、WARNING、ERROR、CRITICAL）

示例：

```bash
python -m src.main --host 0.0.0.0 --port 8080 --log-level DEBUG
```

## API文档

启动服务器后，访问以下URL查看API文档：

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## API端点结构

### REST API

- `/api/news/*`: 新闻相关操作
- `/api/qa/*`: 问答相关操作
- `/api/settings/*`: 设置相关操作

### WebSocket

- `/api/ws/news`: 新闻实时更新
- `/api/ws/qa`: 问答实时流式响应

## 配置

在首次启动前，您需要配置以下API密钥：

- DeepSeek API密钥：用于LLM问答功能
- 火山引擎API密钥：用于新闻分析功能

可以通过API设置这些密钥：

```bash
curl -X POST "http://127.0.0.1:8000/api/settings/api-keys" \
  -H "Content-Type: application/json" \
  -d '{"service": "deepseek", "key": "your-api-key"}'

curl -X POST "http://127.0.0.1:8000/api/settings/api-keys" \
  -H "Content-Type: application/json" \
  -d '{"service": "volcengine", "key": "your-api-key"}'
```

## 开发

此项目使用FastAPI框架。核心功能包括：

- 新闻爬虫和分析
- LLM交互
- WebSocket实时通信
- SQLite数据存储

## 许可证

[许可证信息]
