# tests/test_db/test_qa_repository.py
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
from src.db.repositories import QARepository
from src.db.schema_constants import QA_HISTORY_TABLE

# Ensure a QApplication instance exists if QSql requires it (important for testing)
_app = QApplication.instance() or QApplication([])

# --- Test Data for QA ---
SAMPLE_QA_1 = {
    "question": "如何使用这个应用程序？",
    "answer": "这是一个信息聚合应用程序，您可以通过导航菜单访问不同的功能。",
    "context_ids": "1,2,3",
}
SAMPLE_QA_2 = {
    "question": "如何添加新的新闻来源？",
    "answer": "您可以在设置菜单中找到'添加来源'选项，然后输入来源名称和URL。",
    "context_ids": "4,5",
}
SAMPLE_QA_3 = {
    "question": "如何更改应用主题？",
    "answer": "在设置菜单中，您可以找到'主题设置'选项来更改应用的外观。",
    "context_ids": None,
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


class TestQARepository(unittest.TestCase):
    """Test suite for the QARepository class."""

    db_manager: DatabaseConnectionManager
    db: QSqlDatabase
    repo: QARepository
    db_fd = None  # File descriptor for temp file
    db_path = None  # Path to temp file
    _original_global_config = None  # To store original config

    @classmethod
    def setUpClass(cls):
        """Set up for all tests in this class (runs once)."""
        print("setUpClass: Setting up temporary database...")

        # 1. Create temporary DB file
        cls.db_fd, cls.db_path = tempfile.mkstemp(suffix=".db", prefix="test_qa_repo_")
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
        cls.repo = QARepository()
        print("setUpClass: QARepository instance created.")

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
        print(f"\nsetUp ({self._testMethodName}): Clearing {QA_HISTORY_TABLE} table...")
        query = QSqlQuery(self.db)
        if not query.exec(f"DELETE FROM {QA_HISTORY_TABLE}"):
            # Use assertFailure for critical setup steps
            self.fail(
                f"setUp ({self._testMethodName}): Failed to clear table: {query.lastError().text()}"
            )
        # Optionally reset sequence (might not be strictly needed for in-memory)
        query.exec(
            f"DELETE FROM sqlite_sequence WHERE name='{QA_HISTORY_TABLE}'"
        )  # Ignore errors
        print(f"setUp ({self._testMethodName}): Table cleared.")

    # --- Helper Methods ---
    def _add_sample_qa(self, qa_data: Dict[str, str]) -> int:
        """Adds a sample QA entry and returns its ID."""
        new_id = self.repo.add_qa(
            qa_data["question"], qa_data["answer"], qa_data.get("context_ids")
        )
        self.assertIsNotNone(
            new_id, f"Failed to add sample QA: {qa_data.get('question')[:20]}..."
        )
        self.assertIsInstance(new_id, int)
        return new_id

    def _get_row_count(self) -> int:
        """Gets the current row count in the qa_history table."""
        query = QSqlQuery(f"SELECT COUNT(*) FROM {QA_HISTORY_TABLE}", self.db)
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
    def test_01_add_qa(self):
        """Test adding a new QA entry."""
        print(f"Running {self._testMethodName}...")
        initial_count = self._get_row_count()
        self.assertEqual(initial_count, 0)

        # Add QA with context IDs
        new_id = self.repo.add_qa(
            SAMPLE_QA_1["question"], SAMPLE_QA_1["answer"], SAMPLE_QA_1["context_ids"]
        )

        self.assertIsNotNone(new_id)
        self.assertIsInstance(new_id, int)
        self.assertEqual(self._get_row_count(), 1)

        # Add QA without context IDs
        new_id2 = self.repo.add_qa(
            SAMPLE_QA_3["question"], SAMPLE_QA_3["answer"], None  # No context IDs
        )

        self.assertIsNotNone(new_id2)
        self.assertIsInstance(new_id2, int)
        self.assertEqual(self._get_row_count(), 2)

        # Verify the entries can be retrieved
        all_qa = self.repo.get_all_qa(limit=10)
        self.assertEqual(len(all_qa), 2)

    def test_02_get_all_qa(self):
        """Test retrieving all QA entries with pagination."""
        print(f"Running {self._testMethodName}...")
        # Add sample QA entries (in reverse chronological order to test sorting)
        id3 = self._add_sample_qa(SAMPLE_QA_3)
        id2 = self._add_sample_qa(SAMPLE_QA_2)
        id1 = self._add_sample_qa(SAMPLE_QA_1)
        self.assertEqual(self._get_row_count(), 3)

        # Get all QA entries (should be ordered by created_date DESC)
        all_qa = self.repo.get_all_qa(limit=10)

        # Verify count and order
        self.assertEqual(len(all_qa), 3)

        # Most recent first (assuming add_qa sets created_date to current time)
        # This test might be unreliable if all entries have the same timestamp due to test speed
        # We rely on the fact that the implementation sorts by created_date DESC
        self.assertEqual(all_qa[0]["id"], id1)
        self.assertEqual(all_qa[1]["id"], id2)
        self.assertEqual(all_qa[2]["id"], id3)

        # Test with limit
        limited_qa = self.repo.get_all_qa(limit=2)
        self.assertEqual(len(limited_qa), 2)
        self.assertEqual(limited_qa[0]["id"], id1)
        self.assertEqual(limited_qa[1]["id"], id2)

        # Test with offset
        offset_qa = self.repo.get_all_qa(limit=2, offset=1)
        self.assertEqual(len(offset_qa), 2)
        self.assertEqual(offset_qa[0]["id"], id2)
        self.assertEqual(offset_qa[1]["id"], id3)

    def test_03_delete_qa(self):
        """Test deleting a specific QA entry."""
        print(f"Running {self._testMethodName}...")
        # Add sample QA entries
        id1 = self._add_sample_qa(SAMPLE_QA_1)
        id2 = self._add_sample_qa(SAMPLE_QA_2)
        self.assertEqual(self._get_row_count(), 2)

        # Delete one entry
        deleted = self.repo.delete_qa(id1)

        # Verify deletion was successful
        self.assertTrue(deleted)
        self.assertEqual(self._get_row_count(), 1)

        # Verify the remaining entry
        remaining_qa = self.repo.get_all_qa(limit=10)
        self.assertEqual(len(remaining_qa), 1)
        self.assertEqual(remaining_qa[0]["id"], id2)

        # Test deleting non-existent entry
        non_existent_delete = self.repo.delete_qa(999)
        self.assertFalse(non_existent_delete)
        self.assertEqual(self._get_row_count(), 1)

    def test_04_clear_history(self):
        """Test clearing all QA history."""
        print(f"Running {self._testMethodName}...")
        # Add sample QA entries
        self._add_sample_qa(SAMPLE_QA_1)
        self._add_sample_qa(SAMPLE_QA_2)
        self._add_sample_qa(SAMPLE_QA_3)
        self.assertEqual(self._get_row_count(), 3)

        # Clear all history
        cleared = self.repo.clear_history()

        # Verify all entries were deleted
        self.assertTrue(cleared)
        self.assertEqual(self._get_row_count(), 0)

        # Verify get_all_qa returns empty list
        empty_qa = self.repo.get_all_qa(limit=10)
        self.assertEqual(len(empty_qa), 0)

        # Test clearing empty table
        empty_clear = self.repo.clear_history()
        self.assertTrue(empty_clear)


if __name__ == "__main__":
    print("Starting QARepository tests...")
    unittest.main()
