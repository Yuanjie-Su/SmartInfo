# SmartInfo - 智能资讯分析与知识管理工具

[![GitHub stars](https://img.shields.io/github/stars/catorsu/SmartInfo?style=social)](https://github.com/catorsu/SmartInfo/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/catorsu/SmartInfo?style=social)](https://github.com/catorsu/SmartInfo/network/members)
[![GitHub issues](https://img.shields.io/github/issues/catorsu/SmartInfo)](https://github.com/catorsu/SmartInfo/issues)

**仓库地址:** [https://github.com/catorsu/SmartInfo.git](https://github.com/catorsu/SmartInfo.git)

## 概述

SmartInfo 是一款桌面应用程序，旨在帮助研究人员、分析师和技术爱好者聚合来自各种来源的新闻资讯，利用大语言模型（LLM）进行智能分析和摘要，并构建一个可搜索的知识库以支持问答功能。

该应用程序采用 PySide6 构建了用户友好的界面，允许用户管理资讯源、获取文章、查看内容、触发 AI 驱动的分析，并与基于所收集信息的问答系统进行交互。

## 主要功能

- **资讯管理:**
  - 按主题分类配置和管理资讯源（URLs）。
  - 使用网页抓取 (`crawl4ai`) 从配置的来源获取新闻文章。
  - 利用 LLM（例如 DeepSeek）从抓取的内容中提取关键信息（标题、链接、摘要、日期）。
  - 查看、筛选、搜索和删除存储的新闻文章。
  - 预览新闻内容和 AI 分析结果。
- **智能分析:**
  - 使用 LLM (DeepSeek) 对选定的新闻文章生成摘要并执行不同类型的分析（例如，技术分析、趋势洞察、竞争分析）。
  - 并排查看原始内容和生成的分析报告。
- **知识库问答:**
  - 使用 Sentence Transformers 自动为新闻内容生成向量嵌入。
  - 将嵌入存储在 ChromaDB 向量数据库中以进行语义搜索。
  - 基于收集到的新闻提出自然语言问题。
  - 从知识库中检索相关上下文，并使用 LLM 生成答案。
  - 查看问答历史记录。
- **配置管理:**
  - 通过 UI（存储在数据库中）或环境变量（`.env` 文件优先）管理 API 密钥（例如 DeepSeek）。
  - 配置用于知识库的嵌入模型。
  - 管理新闻分类和资讯源。
  - 查看并可能更改数据存储路径（默认：`~/SmartInfo/data`）。

## 技术栈

- **语言:** Python 3.x
- **图形界面:** PySide6
- **LLM 交互:** `openai` 库 (兼容 DeepSeek API), `deepseek-tokenizer`
- **网页抓取:** `crawl4ai`
- **数据库:**
  - SQLite (用于元数据、配置、问答历史)
  - ChromaDB (用于向量嵌入)
- **嵌入:** `sentence-transformers`
- **配置:** `python-dotenv`
- **其他:** `requests` (用于 API 测试), `ijson` (可能用于流式 JSON 解析)

## 安装

1.  **克隆仓库:**
    ```bash
    git clone [https://github.com/catorsu/SmartInfo.git](https://github.com/catorsu/SmartInfo.git)
    cd SmartInfo
    ```
2.  **创建并激活虚拟环境 (推荐):**
    ```bash
    python -m venv venv
    # Windows 系统
    venv\Scripts\activate
    # macOS/Linux 系统
    source venv/bin/activate
    ```
3.  **安装依赖:**
    ```bash
    pip install -r requirements.txt
    ```
    - 关键依赖可能包括: `PySide6`, `requests`, `python-dotenv`, `crawl4ai`, `chromadb`, `sentence-transformers`, `openai`, `deepseek-tokenizer`, `ijson`。

## 配置

1.  **API 密钥:**
    - 配置 DeepSeek API 密钥的主要方法是通过环境变量。在项目根目录下创建一个名为 `.env` 的文件。
    - 将您的 API 密钥添加到 `.env` 文件中：
      ```dotenv
      # .env 文件内容
      DEEPSEEK_API_KEY=your_deepseek_api_key_here
      ```
    - 或者，您也可以通过应用程序 UI 中的“设置”选项卡设置 API 密钥。通过 UI 设置的密钥存储在 SQLite 数据库 (`smartinfo.db`) 中。**注意:** 如果 `.env` 文件存在，其设置将始终优先。
2.  **其他设置:**
    - 嵌入模型、数据目录和其他系统设置可以在应用程序的“设置”选项卡中查看和修改。
    - 通过 UI 更改的设置将保存在数据目录下的 `smartinfo.db` SQLite 数据库中。
    - 默认数据目录是 `~/SmartInfo/data` （位于您的用户主目录下）。

## 使用方法

1.  确保您已配置好 API 密钥（参见配置部分）。
2.  确保您位于项目的根目录 (`SmartInfo`)。
3.  运行主应用程序脚本：
    ```bash
    python src/main.py
    ```

## 命令行参数

从项目根目录运行时，应用程序支持以下命令行参数：

- `python src/main.py --reset-sources`: (功能可能需要在 `NewsService` 中实现) 将资讯源重置为默认值。
- `python src/main.py --clear-news`: 清除 SQLite 中的所有新闻数据和 ChromaDB 中的嵌入（会提示确认）。
- `python src/main.py --reset-database`: 重置整个数据库，清除所有数据，包括配置、API 密钥、新闻、嵌入和问答历史（会提示确认）。
- `python src/main.py --log-level <LEVEL>`: 设置日志记录级别 (例如 `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`)。默认为 `INFO`。日志文件为 `smartinfo.log`。

## 项目结构

- `src/main.py`: 主程序入口。
- `src/config.py`: 应用程序配置管理。
- `src/core/crawler.py`: 网页抓取逻辑。
- `src/db/`: 数据库连接和 Repository 类。
- `src/services/`: 业务逻辑层 (资讯, 分析, 问答, 设置, LLM 客户端)。
- `src/ui/`: 用户界面组件 (主窗口, 标签页, 异步运行器)。
- `src/utils/`: 工具函数 (例如 Token 计算)。
- `requirements.txt`: 项目依赖项列表。
- `README.md` / `README_CN.md`: 本文档。
