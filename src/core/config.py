import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API Keys
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# Database path (can be made configurable too)
# Example: Get database path from environment or use a default
DEFAULT_DB_PATH = os.getenv(
    "DATABASE_PATH",
    os.path.join(os.path.expanduser("~"), "SmartInfo", "data", "smartinfo.db"),
)

# Other configurations can be added here
# e.g., LLM model names, crawler settings

if not DEEPSEEK_API_KEY:
    print("Warning: DEEPSEEK_API_KEY is not set in the .env file.")
