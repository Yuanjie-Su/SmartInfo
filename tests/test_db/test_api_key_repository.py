# tests/test_db/test_api_key_repository.py
import unittest
import os
import sys
import tempfile
import time
from typing import Dict, Any, List, Tuple

# --- Adjust sys.path to find src ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(
    os.path.dirname(current_dir)
)  # Adjust based on your test dir location
if project_root not in sys.path:
    sys.path.insert(0, project_root)
# ------------------------------------

from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import QApplication

# --- Import the config module itself ---
import src.config  # Needed to access/replace _global_config

# Import necessary components AFTER path adjustment
from src.config import AppConfig, CONFIG_KEY_DATA_DIR, init_config
from src.db.connection import (
    init_db_connection,
    DatabaseConnectionManager,
    MAIN_DB_CONNECTION_NAME,
    get_db,
)
from src.db.repositories import ApiKeyRepository
from src.db.schema_constants import API_CONFIG_TABLE

# Ensure a QApplication instance exists if QSql requires it (important for testing)
_app = QApplication.instance() or QApplication([])

# --- Test Data for API Keys ---
SAMPLE_API_1 = {"name": "openai", "key": "sk-test1234567890abcdef"}
SAMPLE_API_2 = {"name": "googleai", "key": "google-test1234567890abcdef"}
SAMPLE_API_3 = {"name": "anthropic", "key": "anthro-test1234567890abcdef"}


# --- Mock AppConfig (Adapted from test_news_repository.py) ---
class MockConfig(AppConfig):
    def __init__(self, db_path):
        self._persistent_config = self.DEFAULT_PERSISTENT_CONFIG.copy()
        self._secrets = {}
        self._data_dir = os.path.dirname(db_path)  # Use the directory of the temp file
        self._db_path = db_path

    def _load_secrets_from_env(self):
        pass  # Prevent loading real secrets

    def _ensure_data_dir(self):
        pass  # Prevent creating real data dirs

    def _load_from_db(self):
        pass  # Prevent loading from real DB

    def save_persistent(self) -> bool:
        return True


class TestApiKeyRepository(unittest.TestCase):
    """Test suite for the ApiKeyRepository class."""

    db_manager: DatabaseConnectionManager
    db: QSqlDatabase
    repo: ApiKeyRepository
    db_fd = None  # File descriptor for temp file
    db_path = None  # Path to temp file
    _original_global_config = None  # To store original config

    @classmethod
    def setUpClass(cls):
        """Set up for all tests in this class (runs once)."""
        print("setUpClass: Setting up temporary database...")

        # 1. Create temporary DB file
        cls.db_fd, cls.db_path = tempfile.mkstemp(
            suffix=".db", prefix="test_apikey_repo_"
        )
        print(f"setUpClass: Created temporary database file: {cls.db_path}")

        # 2. Mock the global config
        cls._original_global_config = src.config._global_config  # Store original
        mock_config = MockConfig(cls.db_path)
        src.config._global_config = mock_config  # Replace global singleton
        print(
            f"setUpClass: Overrode global config with MockConfig. DB path now: {src.config.get_config().db_path}"
        )

        # 3. Force re-initialization of the DB connection manager singleton
        if DatabaseConnectionManager._instance:
            print("setUpClass: Cleaning up existing DB Manager instance...")
            DatabaseConnectionManager._instance._cleanup()
            DatabaseConnectionManager._instance = None

        # 4. Initialize the DB connection (will use the mocked config)
        try:
            print("setUpClass: Initializing DB Connection Manager for testing...")
            cls.db_manager = init_db_connection()
            cls.db = get_db()
            print("setUpClass: DB Connection Manager Initialized.")
        except Exception as e:
            print(f"FATAL: Error during DB setup in setUpClass: {e}", file=sys.stderr)
            # Cleanup before raising
            if QSqlDatabase.contains(MAIN_DB_CONNECTION_NAME):
                db = QSqlDatabase.database(MAIN_DB_CONNECTION_NAME)
                if db.isOpen():
                    db.close()
                QSqlDatabase.removeDatabase(MAIN_DB_CONNECTION_NAME)
            if cls.db_path and os.path.exists(cls.db_path):
                os.remove(cls.db_path)
            if cls.db_fd:
                os.close(cls.db_fd)
            src.config._global_config = cls._original_global_config  # Restore config
            raise ConnectionError(
                f"Failed to initialize DB connection for testing: {e}"
            ) from e

        if not cls.db or not cls.db.isOpen():
            raise ConnectionError("Database connection failed to open in setUpClass")

        print(f"setUpClass: Temporary database '{cls.db.databaseName()}' connected.")

        # 5. Create the repository instance *after* DB is set up
        cls.repo = ApiKeyRepository()
        print("setUpClass: ApiKeyRepository instance created.")

    @classmethod
    def tearDownClass(cls):
        """Tear down after all tests in this class (runs once)."""
        print("\ntearDownClass: Cleaning up...")
        if hasattr(cls, "db_manager") and cls.db_manager:
            print("tearDownClass: Cleaning up DB Connection Manager...")
            cls.db_manager._cleanup()
            # Check if connection still exists (it shouldn't)
            if QSqlDatabase.contains(MAIN_DB_CONNECTION_NAME):
                print(
                    f"Warning: Connection {MAIN_DB_CONNECTION_NAME} still exists after cleanup."
                )
                QSqlDatabase.removeDatabase(MAIN_DB_CONNECTION_NAME)
            print("tearDownClass: DB Connection Manager cleaned up.")

        if cls.db_fd:
            try:
                os.close(cls.db_fd)
                cls.db_fd = None
            except OSError as e:
                print(f"Warning: Error closing file descriptor: {e}")

        if cls.db_path and os.path.exists(cls.db_path):
            print(f"tearDownClass: Deleting temporary database: {cls.db_path}")
            # Add robust deletion (copied from test_connection.py)
            for _ in range(3):  # Try a few times
                try:
                    os.remove(cls.db_path)
                    print("tearDownClass: Temporary database deleted.")
                    cls.db_path = None
                    break
                except PermissionError:
                    print(
                        f"Warning: Could not delete temp db file (retrying): {cls.db_path}"
                    )
                    time.sleep(0.1)
                except Exception as e:
                    print(f"Error deleting temp db file: {e}")
                    break
            else:
                print(
                    f"Error: Failed to delete temp db file after retries: {cls.db_path}"
                )

        # Restore original config
        if cls._original_global_config:
            src.config._global_config = cls._original_global_config
            print("tearDownClass: Restored original global config.")
        else:
            print("Warning: Original global config was not stored.")

        print("tearDownClass: Cleanup complete.")

    def setUp(self):
        """Set up for each test method (runs before each test)."""
        # Ensure the table is empty before each test for isolation
        print(f"\nsetUp ({self._testMethodName}): Clearing {API_CONFIG_TABLE} table...")
        query = QSqlQuery(self.db)
        if not query.exec(f"DELETE FROM {API_CONFIG_TABLE}"):
            # Use assertFailure for critical setup steps
            self.fail(
                f"setUp ({self._testMethodName}): Failed to clear table: {query.lastError().text()}"
            )
        # Optionally reset sequence (might not be strictly needed for in-memory)
        query.exec(
            f"DELETE FROM sqlite_sequence WHERE name='{API_CONFIG_TABLE}'"
        )  # Ignore errors
        print(f"setUp ({self._testMethodName}): Table cleared.")

    # --- Helper Methods ---
    def _save_sample_api(self, api_data: Dict[str, str]) -> bool:
        """Saves a sample API key and returns success status."""
        result = self.repo.save_key(api_data["name"], api_data["key"])
        self.assertTrue(
            result, f"Failed to save sample API key: {api_data.get('name')}"
        )
        return result

    def _get_row_count(self) -> int:
        """Gets the current row count in the api_config table."""
        query = QSqlQuery(f"SELECT COUNT(*) FROM {API_CONFIG_TABLE}", self.db)
        # Check if query execution was successful before trying to get results
        if not query.exec():
            print(f"Error executing row count query: {query.lastError().text()}")
            return -1
        if query.next():
            return query.value(0)
        # This part should ideally not be reached if exec was successful and table exists
        print("Error getting row count: query.next() returned False")
        return -1  # Indicate error

    # --- Test Cases ---
    def test_01_save_key(self):
        """Test saving a new API key."""
        print(f"Running {self._testMethodName}...")
        initial_count = self._get_row_count()
        self.assertEqual(initial_count, 0)

        # Save a new API key
        result = self.repo.save_key(SAMPLE_API_1["name"], SAMPLE_API_1["key"])

        self.assertTrue(result)
        self.assertEqual(self._get_row_count(), 1)

        # Verify key was saved correctly
        saved_key = self.repo.get_key(SAMPLE_API_1["name"])
        self.assertEqual(saved_key, SAMPLE_API_1["key"])

    def test_02_update_key(self):
        """Test updating an existing API key."""
        print(f"Running {self._testMethodName}...")
        # Save initial API key
        self._save_sample_api(SAMPLE_API_1)
        self.assertEqual(self._get_row_count(), 1)

        # Update the key with new value
        NEW_KEY = "sk-updated9876543210"
        result = self.repo.save_key(SAMPLE_API_1["name"], NEW_KEY)

        # Verify update was successful
        self.assertTrue(result)
        self.assertEqual(self._get_row_count(), 1)  # Count should still be 1

        # Verify key was updated
        updated_key = self.repo.get_key(SAMPLE_API_1["name"])
        self.assertEqual(updated_key, NEW_KEY)
        self.assertNotEqual(
            updated_key, SAMPLE_API_1["key"]
        )  # Should differ from original

    def test_03_get_key(self):
        """Test retrieving an API key."""
        print(f"Running {self._testMethodName}...")
        # Save sample API keys
        self._save_sample_api(SAMPLE_API_1)
        self._save_sample_api(SAMPLE_API_2)

        # Retrieve and verify each key
        key1 = self.repo.get_key(SAMPLE_API_1["name"])
        self.assertEqual(key1, SAMPLE_API_1["key"])

        key2 = self.repo.get_key(SAMPLE_API_2["name"])
        self.assertEqual(key2, SAMPLE_API_2["key"])

        # Test getting non-existent key
        non_existent = self.repo.get_key("non_existent_api")
        self.assertIsNone(non_existent)

    def test_04_delete_key(self):
        """Test deleting an API key."""
        print(f"Running {self._testMethodName}...")
        # Save sample API keys
        self._save_sample_api(SAMPLE_API_1)
        self._save_sample_api(SAMPLE_API_2)
        self.assertEqual(self._get_row_count(), 2)

        # Delete one key
        deleted = self.repo.delete_key(SAMPLE_API_1["name"])

        # Verify deletion was successful
        self.assertTrue(deleted)
        self.assertEqual(self._get_row_count(), 1)

        # Verify the key is no longer retrievable
        key = self.repo.get_key(SAMPLE_API_1["name"])
        self.assertIsNone(key)

        # But the other key still exists
        key2 = self.repo.get_key(SAMPLE_API_2["name"])
        self.assertEqual(key2, SAMPLE_API_2["key"])

        # Test deleting non-existent key
        non_existent_delete = self.repo.delete_key("non_existent_api")
        self.assertFalse(non_existent_delete)
        self.assertEqual(self._get_row_count(), 1)

    def test_05_get_all_keys_info(self):
        """Test retrieving info for all API keys."""
        print(f"Running {self._testMethodName}...")
        # Save sample API keys
        self._save_sample_api(SAMPLE_API_1)
        self._save_sample_api(SAMPLE_API_2)
        self._save_sample_api(SAMPLE_API_3)

        # Get all keys info
        all_keys_info = self.repo.get_all_keys_info()

        # Verify count and content
        self.assertEqual(len(all_keys_info), 3)

        # Each result should have 3 elements: api_name, created_date, modified_date
        for key_info in all_keys_info:
            self.assertEqual(len(key_info), 3)

        # Verify each API name exists in the results
        api_names = [info[0] for info in all_keys_info]
        self.assertIn(SAMPLE_API_1["name"], api_names)
        self.assertIn(SAMPLE_API_2["name"], api_names)
        self.assertIn(SAMPLE_API_3["name"], api_names)

    def test_06_delete_all(self):
        """Test deleting all API keys."""
        print(f"Running {self._testMethodName}...")
        # Save sample API keys
        self._save_sample_api(SAMPLE_API_1)
        self._save_sample_api(SAMPLE_API_2)
        self._save_sample_api(SAMPLE_API_3)
        self.assertEqual(self._get_row_count(), 3)

        # Delete all keys
        all_deleted = self.repo.delete_all()

        # Verify all keys were deleted
        self.assertTrue(all_deleted)
        self.assertEqual(self._get_row_count(), 0)

        # Test deleting from empty table
        empty_delete = self.repo.delete_all()
        self.assertTrue(empty_delete)


if __name__ == "__main__":
    print("Starting ApiKeyRepository tests...")
    unittest.main()
