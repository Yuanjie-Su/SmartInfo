# SmartInfo - 智能资讯分析与知识管理工具

SmartInfo 是一款面向科技研究人员、行业分析师和技术爱好者的智能资讯分析与知识管理工具，专注于前沿技术、学术动态和市场发展等领域。

## 项目状态

当前项目处于初始开发阶段，已完成基础框架的搭建。

已实现的功能：

- 项目基础结构
- 数据库架构设计（SQLite + ChromaDB）
- 用户界面框架（PyQt）
- 示例数据生成

待实现的功能：

- 资讯获取模块完善
- 大模型 API 接口集成
- 智能分析与摘要生成
- 知识库的语义检索和问答功能

## 主要功能

- **资讯获取**：支持配置多个主流资讯源，自定义抓取频率和关注领域
- **智能分析与总结**：通过大模型 API 对资讯进行分析与摘要生成
- **本地知识库**：使用 SQLite 和 ChromaDB 构建高效的本地知识库
- **智能问答**：基于知识库提供语义搜索和对话式问答体验
- **用户友好界面**：简洁直观的界面设计，支持信息搜索、筛选与导出

## 技术架构

- 开发语言：Python 3.9+
- 桌面框架：PySide6 (Qt)
- 数据库：SQLite + ChromaDB
- 大模型 API：DeepSeek
- 嵌入模型：Sentence-Transformers

## 安装与使用

### 环境要求

- Python 3.9 或更高版本
- Windows 10/11 操作系统
- 屏幕分辨率：1920\*1080 及以上

### 安装步骤

1. 克隆本仓库到本地：

```bash
git clone https://github.com/yourusername/SmartInfo.git
cd SmartInfo
```

2. 安装依赖项：

```bash
pip install -r requirements.txt
```

3. 运行应用程序：

```bash
# 首次运行时，可以使用--init-data参数初始化示例数据
python src/main.py --init-data

# 后续运行只需执行
python src/main.py
```

## 项目结构

```
SmartInfo/
├── src/                     # 源代码
│   ├── main.py              # 应用入口
│   ├── modules/             # 功能模块
│   │   ├── news_fetch/      # 资讯获取模块
│   │   ├── analysis/        # 智能分析模块
│   │   ├── knowledge_base/  # 知识库模块
│   │   ├── qa/              # 智能问答模块
│   │   └── ui/              # 用户界面模块
│   ├── database/            # 数据库相关
│   ├── config/              # 配置管理
│   ├── models/              # 数据模型
│   └── utils/               # 工具函数
├── requirements.txt         # 依赖项
└── README.md                # 说明文档
```

## 贡献指南

欢迎对本项目提出改进建议或代码贡献。请遵循以下步骤：

1. Fork 本仓库
2. 创建您的特性分支：`git checkout -b feature/AmazingFeature`
3. 提交您的更改：`git commit -m 'Add some AmazingFeature'`
4. 推送到分支：`git push origin feature/AmazingFeature`
5. 打开一个 Pull Request

## 许可证

MIT License
