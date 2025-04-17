# tests/test_db/test_system_config_repository.py
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
from src.db.repositories import SystemConfigRepository
from src.db.schema_constants import SYSTEM_CONFIG_TABLE

# Ensure a QApplication instance exists if QSql requires it (important for testing)
_app = QApplication.instance() or QApplication([])

# --- Test Data for System Config ---
SAMPLE_CONFIG_1 = {"key": "theme", "value": "dark", "description": "应用程序主题设置"}
SAMPLE_CONFIG_2 = {
    "key": "language",
    "value": "zh-CN",
    "description": "应用程序语言设置",
}
SAMPLE_CONFIG_3 = {
    "key": "refresh_interval",
    "value": "30",
    "description": "数据刷新间隔（分钟）",
}


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


class TestSystemConfigRepository(unittest.TestCase):
    """Test suite for the SystemConfigRepository class."""

    db_manager: DatabaseConnectionManager
    db: QSqlDatabase
    repo: SystemConfigRepository
    db_fd = None  # File descriptor for temp file
    db_path = None  # Path to temp file
    _original_global_config = None  # To store original config

    @classmethod
    def setUpClass(cls):
        """Set up for all tests in this class (runs once)."""
        print("setUpClass: Setting up temporary database...")

        # 1. Create temporary DB file
        cls.db_fd, cls.db_path = tempfile.mkstemp(
            suffix=".db", prefix="test_sysconfig_repo_"
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
        cls.repo = SystemConfigRepository()
        print("setUpClass: SystemConfigRepository instance created.")

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
        print(
            f"\nsetUp ({self._testMethodName}): Clearing {SYSTEM_CONFIG_TABLE} table..."
        )
        query = QSqlQuery(self.db)
        if not query.exec(f"DELETE FROM {SYSTEM_CONFIG_TABLE}"):
            # Use assertFailure for critical setup steps
            self.fail(
                f"setUp ({self._testMethodName}): Failed to clear table: {query.lastError().text()}"
            )
        print(f"setUp ({self._testMethodName}): Table cleared.")

    # --- Helper Methods ---
    def _save_sample_config(self, config_data: Dict[str, str]) -> bool:
        """Saves a sample config and returns success status."""
        result = self.repo.save_config(
            config_data["key"], config_data["value"], config_data.get("description")
        )
        self.assertTrue(
            result, f"Failed to save sample config: {config_data.get('key')}"
        )
        return result

    def _get_row_count(self) -> int:
        """Gets the current row count in the system_config table."""
        query = QSqlQuery(f"SELECT COUNT(*) FROM {SYSTEM_CONFIG_TABLE}", self.db)
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
    def test_01_save_config(self):
        """Test saving a new config."""
        print(f"Running {self._testMethodName}...")
        initial_count = self._get_row_count()
        self.assertEqual(initial_count, 0)

        # Save a new config
        result = self.repo.save_config(
            SAMPLE_CONFIG_1["key"],
            SAMPLE_CONFIG_1["value"],
            SAMPLE_CONFIG_1["description"],
        )

        self.assertTrue(result)
        self.assertEqual(self._get_row_count(), 1)

        # Verify config was saved correctly
        saved_value = self.repo.get_config(SAMPLE_CONFIG_1["key"])
        self.assertEqual(saved_value, SAMPLE_CONFIG_1["value"])

    def test_02_update_config(self):
        """Test updating an existing config."""
        print(f"Running {self._testMethodName}...")
        # Save initial config
        self._save_sample_config(SAMPLE_CONFIG_1)
        self.assertEqual(self._get_row_count(), 1)

        # Update the config with new value
        NEW_VALUE = "light"
        result = self.repo.save_config(
            SAMPLE_CONFIG_1["key"], NEW_VALUE, "Updated description"
        )

        # Verify update was successful
        self.assertTrue(result)
        self.assertEqual(self._get_row_count(), 1)  # Count should still be 1

        # Verify value was updated
        updated_value = self.repo.get_config(SAMPLE_CONFIG_1["key"])
        self.assertEqual(updated_value, NEW_VALUE)
        self.assertNotEqual(
            updated_value, SAMPLE_CONFIG_1["value"]
        )  # Should differ from original

    def test_03_get_config(self):
        """Test retrieving a config."""
        print(f"Running {self._testMethodName}...")
        # Save sample configs
        self._save_sample_config(SAMPLE_CONFIG_1)
        self._save_sample_config(SAMPLE_CONFIG_2)

        # Retrieve and verify each config
        value1 = self.repo.get_config(SAMPLE_CONFIG_1["key"])
        self.assertEqual(value1, SAMPLE_CONFIG_1["value"])

        value2 = self.repo.get_config(SAMPLE_CONFIG_2["key"])
        self.assertEqual(value2, SAMPLE_CONFIG_2["value"])

        # Test getting non-existent config
        non_existent = self.repo.get_config("non_existent_key")
        self.assertIsNone(non_existent)

    def test_04_get_all_configs(self):
        """Test retrieving all configs."""
        print(f"Running {self._testMethodName}...")
        # Save sample configs
        self._save_sample_config(SAMPLE_CONFIG_1)
        self._save_sample_config(SAMPLE_CONFIG_2)
        self._save_sample_config(SAMPLE_CONFIG_3)

        # Get all configs
        all_configs = self.repo.get_all_configs()

        # Verify count and content
        self.assertEqual(len(all_configs), 3)
        self.assertIsInstance(all_configs, dict)

        # Verify each config exists in the results
        self.assertIn(SAMPLE_CONFIG_1["key"], all_configs)
        self.assertIn(SAMPLE_CONFIG_2["key"], all_configs)
        self.assertIn(SAMPLE_CONFIG_3["key"], all_configs)

        # Verify values
        self.assertEqual(all_configs[SAMPLE_CONFIG_1["key"]], SAMPLE_CONFIG_1["value"])
        self.assertEqual(all_configs[SAMPLE_CONFIG_2["key"]], SAMPLE_CONFIG_2["value"])
        self.assertEqual(all_configs[SAMPLE_CONFIG_3["key"]], SAMPLE_CONFIG_3["value"])

    def test_05_delete_config(self):
        """Test deleting a config."""
        print(f"Running {self._testMethodName}...")
        # Save sample configs
        self._save_sample_config(SAMPLE_CONFIG_1)
        self._save_sample_config(SAMPLE_CONFIG_2)
        self.assertEqual(self._get_row_count(), 2)

        # Delete one config
        deleted = self.repo.delete_config(SAMPLE_CONFIG_1["key"])

        # Verify deletion was successful
        self.assertTrue(deleted)
        self.assertEqual(self._get_row_count(), 1)

        # Verify the config is no longer retrievable
        value = self.repo.get_config(SAMPLE_CONFIG_1["key"])
        self.assertIsNone(value)

        # But the other config still exists
        value2 = self.repo.get_config(SAMPLE_CONFIG_2["key"])
        self.assertEqual(value2, SAMPLE_CONFIG_2["value"])

        # Test deleting non-existent config
        non_existent_delete = self.repo.delete_config("non_existent_key")
        self.assertFalse(non_existent_delete)
        self.assertEqual(self._get_row_count(), 1)

    def test_06_delete_all(self):
        """Test deleting all configs."""
        print(f"Running {self._testMethodName}...")
        # Save sample configs
        self._save_sample_config(SAMPLE_CONFIG_1)
        self._save_sample_config(SAMPLE_CONFIG_2)
        self._save_sample_config(SAMPLE_CONFIG_3)
        self.assertEqual(self._get_row_count(), 3)

        # Delete all configs
        all_deleted = self.repo.delete_all()

        # Verify all configs were deleted
        self.assertTrue(all_deleted)
        self.assertEqual(self._get_row_count(), 0)

        # Test deleting from empty table
        empty_delete = self.repo.delete_all()
        self.assertTrue(empty_delete)


if __name__ == "__main__":
    print("Starting SystemConfigRepository tests...")
    unittest.main()
