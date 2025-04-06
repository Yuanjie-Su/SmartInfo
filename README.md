# SmartInfo - Intelligent News Analysis and Knowledge Management Tool

[![GitHub stars](https://img.shields.io/github/stars/catorsu/SmartInfo?style=social)](https://github.com/catorsu/SmartInfo/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/catorsu/SmartInfo?style=social)](https://github.com/catorsu/SmartInfo/network/members)
[![GitHub issues](https://img.shields.io/github/issues/catorsu/SmartInfo)](https://github.com/catorsu/SmartInfo/issues)

**Repository:** [https://github.com/catorsu/SmartInfo.git](https://github.com/catorsu/SmartInfo.git)

## Overview

SmartInfo is a desktop application designed for researchers, analysts, and enthusiasts to aggregate news from various sources, perform intelligent analysis and summarization using Large Language Models (LLMs), and build a searchable knowledge base for question-answering.

The application features a user-friendly interface built with PySide6, allowing users to manage news sources, fetch articles, view content, trigger AI-powered analysis, and interact with a Q&A system based on the collected information.

## Key Features

- **News Management:**
  - Configure and manage news sources (URLs) categorized by topic.
  - Fetch news articles from configured sources using web crawling (`crawl4ai`).
  - Extract key information (title, link, summary, date) from crawled content using an LLM (e.g., DeepSeek).
  - View, filter, search, and delete stored news articles.
  - Preview news content and AI analysis results.
- **Intelligent Analysis:**
  - Generate summaries and perform different types of analysis (e.g., Technical, Trends, Competitive) on selected news articles using an LLM (DeepSeek).
  - View original content alongside the generated analysis.
- **Knowledge Base Q&A:**
  - Automatically generate vector embeddings for news content using Sentence Transformers.
  - Store embeddings in a ChromaDB vector database for semantic search.
  - Ask natural language questions based on the collected news.
  - Retrieve relevant context from the knowledge base and generate answers using an LLM.
  - View Q&A history.
- **Configuration:**
  - Manage API keys (e.g., DeepSeek) via UI (stored in database) or environment variables (`.env` file takes priority).
  - Configure the embedding model used for the knowledge base.
  - Manage news categories and sources.
  - View and potentially change the data storage path (default: `~/SmartInfo/data`).

## Technology Stack

- **Language:** Python 3.x
- **GUI:** PySide6
- **LLM Interaction:** `openai` library (compatible with DeepSeek API), `deepseek-tokenizer`
- **Web Crawling:** `crawl4ai`
- **Database:**
  - SQLite (for metadata, configuration, Q&A history)
  - ChromaDB (for vector embeddings)
- **Embeddings:** `sentence-transformers`
- **Configuration:** `python-dotenv`
- **Other:** `requests` (for API testing), `ijson` (likely for stream parsing)

## Installation

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/catorsu/SmartInfo.git](https://github.com/catorsu/SmartInfo.git)
    cd SmartInfo
    ```
2.  **Create and activate a virtual environment (recommended):**
    ```bash
    python -m venv venv
    # On Windows
    venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    - Key dependencies likely include: `PySide6`, `requests`, `python-dotenv`, `crawl4ai`, `chromadb`, `sentence-transformers`, `openai`, `deepseek-tokenizer`, `ijson`.

## Configuration

1.  **API Keys:**
    - The primary method for configuring the DeepSeek API key is through an environment variable. Create a file named `.env` in the project root directory.
    - Add your API key to the `.env` file:
      ```dotenv
      # .env file
      DEEPSEEK_API_KEY=your_deepseek_api_key_here
      ```
    - Alternatively, you can set the API key via the "Settings" tab in the application UI. Keys set via the UI are stored in the SQLite database (`smartinfo.db`). **Note:** The `.env` file setting always takes priority if present.
2.  **Other Settings:**
    - The embedding model, data directory, and other system settings can be viewed and potentially modified in the "Settings" tab of the application.
    - Settings changed via the UI are saved in the `smartinfo.db` SQLite database located in the data directory.
    - The default data directory is `~/SmartInfo/data` (within your user home directory).

## Usage

1.  Ensure you have configured your API key (see Configuration section).
2.  Make sure you are in the project's root directory (`SmartInfo`).
3.  Run the main application script:
    ```bash
    python src/main.py
    ```

## Command Line Arguments

The application supports the following command-line arguments when run from the root directory:

- `python src/main.py --reset-sources`: (Functionality might need implementation in `NewsService`) Reset news sources to default.
- `python src/main.py --clear-news`: Clear ALL news data from SQLite and embeddings from ChromaDB (prompts for confirmation).
- `python src/main.py --reset-database`: Reset the entire database, clearing ALL data including configuration, API keys, news, embeddings, and Q&A history (prompts for confirmation).
- `python src/main.py --log-level <LEVEL>`: Set the logging level (e.g., `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). Default is `INFO`. Log file is `smartinfo.log`.

## Project Structure

- `src/main.py`: Main application entry point.
- `src/config.py`: Application configuration management.
- `src/core/crawler.py`: Web crawling logic.
- `src/db/`: Database connection and repository classes.
- `src/services/`: Business logic layer (News, Analysis, QA, Settings, LLM Client).
- `src/ui/`: User interface components (Main Window, Tabs, Async Runner).
- `src/utils/`: Utility functions (e.g., token counting).
- `requirements.txt`: Project dependencies.
- `README.md` / `README_CN.md`: This documentation.
