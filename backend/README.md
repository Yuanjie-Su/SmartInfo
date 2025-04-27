# SmartInfo Backend

This is the FastAPI backend for the SmartInfo project, an intelligent news analysis and knowledge management tool.

## Development

### Project Structure

```
backend/
├── api/
│   ├── v1/              # Versioned API endpoints
│   │   ├── routers/     # Specific routers (chat, news, settings)
│   │   │   ├── chat.py
│   │   │   ├── news.py
│   │   │   └── settings.py
│   │   └── __init__.py
│   ├── dependencies/    # FastAPI dependency injection
│   │   └── common.py
│   └── __init__.py      # Main API router assembly
├── core/                # Core functionality (e.g., crawler, LLM client, utilities)
│   ├── crawler.py
│   ├── llm/             # LLM interaction specific modules
│   │   ├── client.py
│   │   └── pool.py
│   ├── utils/           # General utilities
│   │   ├── html_utils.py
│   │   ├── markdown_utils.py
│   │   ├── parse.py
│   │   ├── prompt.py
│   │   ├── text_utils.py
│   │   └── token_utils.py
│   └── __init__.py
├── db/                  # Database layer
│   ├── repositories/    # Data repositories (CRUD operations)
│   │   ├── api_key.py
│   │   ├── base.py
│   │   ├── chat.py
│   │   ├── message.py
│   │   ├── news.py
│   │   ├── news_category.py
│   │   ├── news_source.py
│   │   ├── system_config.py
│   │   └── __init__.py
│   ├── connection.py      # Database connection management
│   ├── schema_constants.py # Database schema constants
│   └── __init__.py
├── models/              # Pydantic models for data validation and serialization
│   ├── api_key.py
│   ├── chat.py
│   ├── news.py
│   ├── settings.py
│   └── __init__.py
├── services/            # Business logic layer
│   ├── chat_service.py
│   ├── news_service.py
│   ├── setting_service.py
│   └── __init__.py
├── config.py            # Application configuration loading and access
├── main.py              # FastAPI application entry point and lifespan management
├── requirements.txt     # Project dependencies
└── README.md            # Project README
```
