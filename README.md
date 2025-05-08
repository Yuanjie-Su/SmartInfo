# SmartInfo: News Aggregation, Analysis, and Chat

[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Framework](https://img.shields.io/badge/Framework-FastAPI%20%7C%20Next.js-lightgrey.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE) SmartInfo is a full-stack application designed for intelligent news aggregation, automated content analysis using Large Language Models (LLMs), and interactive chat functionalities. It comprises a FastAPI backend for data processing and API management, and a React/Next.js frontend for a modern user experience.

## ✨ Features

* **Backend (FastAPI)**
    * User authentication and management (JWT-based).
    * News source and category management (CRUD operations per user).
    * Asynchronous web crawling (Aiohttp, Playwright, Selenium) for fetching news content.
    * Background task processing using Celery and Redis for fetching and analyzing news.
    * Integration with OpenAI-compatible LLM APIs for:
        * Extracting relevant article links from source pages.
        * Generating concise summaries and fact-based titles for articles.
        * Performing in-depth analysis of news content on demand.
        * Powering a conversational chat interface.
    * WebSocket support for real-time task progress monitoring.
    * API key management for user-specific LLM configurations.
    * Persistent user preference storage.
    * PostgreSQL database integration using `asyncpg`.
    * Comprehensive API documentation via Swagger UI and ReDoc.
* **Frontend (Next.js & Ant Design)**
    * User registration and login interface.
    * Dashboard for viewing, filtering, and searching aggregated news items.
    * Modal interface to trigger background news fetching from selected sources.
    * Real-time task progress drawer using WebSockets.
    * Modal for viewing detailed LLM analysis of individual news items.
    * Interactive chat interface with conversation history management.
    * Settings page for managing API keys and application preferences.
    * Protected routes using Higher-Order Components (HOC).
    * Responsive design using Ant Design components.

## 🛠️ Technology Stack

**Backend:**

* **Framework:** FastAPI
* **Language:** Python 3.12+
* **Async:** `asyncio`, `aiohttp`, `asyncpg`
* **Database:** PostgreSQL
* **Task Queue:** Celery
* **Broker/Backend:** Redis
* **Web Crawling:** Playwright, Selenium, Aiohttp, Trafilatura, BeautifulSoup4
* **LLM Interaction:** OpenAI Python SDK (compatible with DeepSeek, etc.)
* **Authentication:** JWT (python-jose), Bcrypt
* **Data Validation:** Pydantic
* **Environment Management:** Poetry, python-dotenv
* **Web Server:** Uvicorn

**Frontend:**

* **Framework:** Next.js
* **Language:** TypeScript
* **UI Library:** Ant Design (antd)
* **State Management:** React Context API (`AuthContext`)
* **HTTP Client:** Axios
* **Testing:** Jest, React Testing Library
* **Package Manager:** npm / yarn

## 📂 Project Structure

```
SmartInfo/
├── backend/                 # FastAPI Backend Application
│   ├── api/                 # API routers and dependencies
│   │   ├── dependencies/
│   │   └── routers/         # Routers for different modules (auth, chat, news, etc.)
│   ├── background/          # Celery background tasks and app setup
│   │   ├── tasks/
│   │   └── celery_app.py
│   ├── core/                # Core logic (LLM client, security, crawler, workflow)
│   │   ├── llm/
│   │   ├── workflow/
│   │   └── ...
│   ├── db/                  # Database connection, repositories, schema constants
│   │   ├── repositories/
│   │   └── ...
│   ├── models/              # Pydantic models (schemas)
│   │   └── schemas/
│   ├── services/            # Business logic layer
│   ├── utils/               # Utility functions
│   ├── config.py            # Application configuration loading
│   ├── main.py              # FastAPI application entry point
│   └── pyproject.toml       # Poetry dependencies and project config
├── frontend/                # Next.js Frontend Application
│   ├── public/              # Static assets
│   ├── src/                 # Source code
│   │   ├── components/      # Reusable React components
│   │   ├── context/         # React context (e.g., AuthContext)
│   │   ├── pages/           # Next.js pages (routes)
│   │   ├── services/        # API service functions (using Axios)
│   │   ├── styles/          # CSS modules and global styles
│   │   ├── utils/           # Utility functions and types
│   │   └── __tests__/       # Unit/Integration tests
│   ├── next.config.js       # Next.js configuration
│   ├── package.json         # npm/yarn dependencies
│   └── tsconfig.json        # TypeScript configuration
├── .gitignore               # Git ignore rules
└── README.md                # This file
```

## 🚀 Getting Started

### Prerequisites

* Python 3.12+
* Poetry (for Python dependency management)
* Node.js (v18+ recommended)
* npm or yarn
* PostgreSQL Database Server
* Redis Server

### Backend Setup

1.  **Navigate to Backend Directory:**
    ```bash
    cd backend
    ```

2.  **Install Dependencies:**
    ```bash
    poetry install
    ```
    *(This installs dependencies defined in `pyproject.toml` into a virtual environment managed by Poetry)*

3.  **Environment Variables:**
    * Copy the example environment file:
        ```bash
        cp .env.example .env
        ```
    * Edit the `.env` file and provide your specific database credentials, Redis URL, and a strong `SECRET_KEY` for JWT:
        ```dotenv
        # .env (Example - Replace with your actual values)
        DB_USER=your_db_user
        DB_PASSWORD=your_db_password
        DB_NAME=smartinfo_db
        DB_HOST=localhost
        DB_PORT=5432
        REDIS_URL=redis://localhost:6379/0       # For Celery Broker & WebSocket PubSub
        REDIS_BACKEND_URL=redis://localhost:6379/1 # For Celery Result Backend
        SECRET_KEY=a_very_strong_random_secret_key_please_change_me # IMPORTANT: Change this!
        FETCH_BATCH_SIZE=5 # Number of sources to fetch in one Celery task
        # LOG_LEVEL=DEBUG # Optional: Set to DEBUG for more verbose logs
        # RELOAD=true # Optional: Set to true for auto-reload during development
        ```

4.  **Run Database Migrations (Implicit):**
    The database tables are created automatically when the FastAPI application starts (within the `lifespan` function in `main.py`) if they don't exist.

5.  **Run the Backend API Server:**
    ```bash
    poetry run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
    ```
    * `--reload`: Enables auto-reloading for development. Remove for production.
    * The server will be accessible at `http://localhost:8000`.

6.  **Run the Celery Worker:**
    Open a *new terminal* in the `backend` directory:
    ```bash
    poetry run celery -A backend.background.celery_app worker --loglevel=info
    ```
    *(This starts the background worker to process news fetching and analysis tasks.)*

### Frontend Setup

1.  **Navigate to Frontend Directory:**
    ```bash
    cd frontend
    ```

2.  **Install Dependencies:**
    ```bash
    npm install
    # or
    yarn install
    ```

3.  **Environment Variables:**
    * Create a `.env.local` file in the `frontend` directory.
    * Add the URL of your running backend API:
        ```dotenv
        # .env.local
        NEXT_PUBLIC_API_URL=http://localhost:8000
        ```
        *(Adjust if your backend is running on a different host or port)*

4.  **Run the Frontend Development Server:**
    ```bash
    npm run dev
    # or
    yarn dev
    ```
    * The frontend will be accessible at `http://localhost:3000`.

### Testing

**Backend:**

* Run unit/integration tests:
    ```bash
    cd backend
    poetry run pytest
    ```

**Frontend:**

* Run unit tests:
    ```bash
    cd frontend
    npm test
    # or
    yarn test
    ```
* Test backend connectivity from the frontend environment:
    ```bash
    cd frontend
    npm run test:backend
    # or
    yarn test:backend
    ```
    *(Requires the backend server to be running)*

## 📚 API Documentation

Once the backend server is running, you can access the automatically generated API documentation:

* **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
* **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

## 🤝 Contributing

Contributions are welcome! Please follow standard fork-and-pull-request workflows. Ensure your code adheres to existing style conventions and includes tests where appropriate.

## 📜 License

This project is licensed under the MIT License. See the `LICENSE` file for details. ```