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
- **Q&A:**
  - Ask natural language questions based on the collected news.
  - View Q&A history.
- **Configuration:**
  - Manage API keys (e.g., DeepSeek) via UI (stored in database) or environment variables (`.env` file takes priority).
  - Manage news categories and sources.
  - View and potentially change the data storage path (default: `~/SmartInfo/data`).

## Technology Stack

- **Language:** Python 3.x
- **GUI:** PySide6
- **LLM Interaction:** `openai` library (compatible with DeepSeek API), `deepseek-tokenizer`
- **Web Crawling:** `crawl4ai`
- **Database:**
  - SQLite (for metadata, configuration, Q&A history)
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
- `python src/main.py --reset-database`: Reset the entire database, clearing ALL data including configuration, API keys, news and Q&A history (prompts for confirmation).
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

## Running Background Tasks with Celery

The application uses Celery with Redis for handling background tasks such as news fetching and analysis. To run these tasks, you need to start a Celery worker in addition to the main FastAPI application.

### Starting the Celery Worker

1. Make sure Redis is running on localhost:6379 (or configure the REDIS_URL environment variable)
2. Open a terminal and navigate to the project directory
3. Activate your virtual environment
4. Run the following command:

```bash
# On Windows
celery -A backend.celery_worker worker --loglevel=info --pool=solo

# On Linux/Mac
celery -A backend.celery_worker worker --loglevel=info
```

The worker will start and initialize all the necessary dependencies (database connection, LLM client pool, etc.) and then start listening for tasks.

Note: On Windows, you need to use the `--pool=solo` option as the default prefork pool is not supported on Windows.

### Configuring Redis

By default, the application looks for Redis at `redis://localhost:6379/0`. You can change this by setting the `REDIS_URL` environment variable in your `.env` file:

```
REDIS_URL=redis://your-redis-host:6379/0
```
