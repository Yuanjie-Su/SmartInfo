# tests/db/repositories/test_news_repository.py
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
from src.db.repositories import NewsRepository
from src.db.schema_constants import NEWS_TABLE

# Ensure a QApplication instance exists if QSql requires it (important for testing)
_app = QApplication.instance() or QApplication([])

# --- Test Data (Keep as before) ---
SAMPLE_NEWS_1: Dict[str, Any] = {
    "title": "Test Article 1",
    "link": "http://example.com/test1",
    "source_name": "TestSource",
    "category_name": "TestCategory",
    "source_id": 10,
    "category_id": 1,
    "summary": "Summary 1",
    "analysis": "Analysis 1",
    "date": "2025-04-15 10:00:00",
}
SAMPLE_NEWS_2: Dict[str, Any] = {
    "title": "Test Article 2",
    "link": "http://example.com/test2",
    "source_name": "TestSource",
    "category_name": "TestCategory",
    "source_id": 10,
    "category_id": 1,
    "summary": "Summary 2",
    "analysis": "Analysis 2",
    "date": "2025-04-16 11:00:00",
}
SAMPLE_NEWS_3: Dict[str, Any] = {
    "title": "Test Article 3",
    "link": "http://example.com/test3",
    "source_name": "AnotherSource",
    "category_name": "AnotherCategory",
    "source_id": 11,
    "category_id": 2,
    "summary": "Summary 3",
    "analysis": "Analysis 3",
    "date": "2025-04-16 12:00:00",
}
INVALID_NEWS_NO_LINK: Dict[str, Any] = {
    "title": "Invalid Article No Link",
    "source_name": "TestSource",
    "category_name": "TestCategory",
}
INVALID_NEWS_NO_TITLE: Dict[str, Any] = {
    "link": "http://example.com/no-title",
    "source_name": "TestSource",
    "category_name": "TestCategory",
}
# --- End Test Data ---


# --- Mock AppConfig (Adapted from test_connection.py) ---
class MockConfig(AppConfig):
    def __init__(self, db_path):
        self._persistent_config = self.DEFAULT_PERSISTENT_CONFIG.copy()
        self._secrets = {}
        self._data_dir = os.path.dirname(db_path)  # Use the directory of the temp file
        self._db_path = db_path
        # print(f"MockConfig initialized with DB path: {self._db_path}") # Optional debug print

    def _load_secrets_from_env(self):
        pass  # Prevent loading real secrets

    def _ensure_data_dir(self):
        pass  # Prevent creating real data dirs

    def _load_from_db(self):
        pass  # Prevent loading from real DB

    def save_persistent(self) -> bool:
        # Don't actually save during tests using mock
        # print("MockConfig.save_persistent called (no action taken).")
        return True


# --- End Mock AppConfig ---


class TestNewsRepository(unittest.TestCase):
    """Test suite for the NewsRepository class."""

    db_manager: DatabaseConnectionManager
    db: QSqlDatabase
    repo: NewsRepository
    db_fd = None  # File descriptor for temp file
    db_path = None  # Path to temp file
    _original_global_config = None  # To store original config

    @classmethod
    def setUpClass(cls):
        """Set up for all tests in this class (runs once)."""
        print("setUpClass: Setting up temporary database...")

        # 1. Create temporary DB file
        cls.db_fd, cls.db_path = tempfile.mkstemp(
            suffix=".db", prefix="test_news_repo_"
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
        cls.repo = NewsRepository()
        print("setUpClass: NewsRepository instance created.")

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
        print(f"\nsetUp ({self._testMethodName}): Clearing {NEWS_TABLE} table...")
        query = QSqlQuery(self.db)
        if not query.exec(f"DELETE FROM {NEWS_TABLE}"):
            # Use assertFailure for critical setup steps
            self.fail(
                f"setUp ({self._testMethodName}): Failed to clear table: {query.lastError().text()}"
            )
        # Optionally reset sequence (might not be strictly needed for in-memory)
        query.exec(
            f"DELETE FROM sqlite_sequence WHERE name='{NEWS_TABLE}'"
        )  # Ignore errors
        print(f"setUp ({self._testMethodName}): Table cleared.")

    # --- Helper Methods (Keep as before) ---
    def _add_sample_news(self, sample_data: Dict[str, Any]) -> int:
        """Adds a sample news item and returns its ID."""
        new_id = self.repo.add(sample_data)
        self.assertIsNotNone(
            new_id, f"Failed to add sample news: {sample_data.get('link')}"
        )
        self.assertIsInstance(new_id, int)
        return new_id

    def _get_row_count(self) -> int:
        """Gets the current row count in the news table."""
        query = QSqlQuery(f"SELECT COUNT(*) FROM {NEWS_TABLE}", self.db)
        # Check if query execution was successful before trying to get results
        if not query.exec():
            print(f"Error executing row count query: {query.lastError().text()}")
            return -1
        if query.next():
            return query.value(0)
        # This part should ideally not be reached if exec was successful and table exists
        print("Error getting row count: query.next() returned False")
        return -1  # Indicate error

    # --- Test Cases (Keep as before) ---

    def test_01_add_single_valid(self):
        """Test adding a single valid news item."""
        print(f"Running {self._testMethodName}...")
        initial_count = self._get_row_count()
        self.assertEqual(initial_count, 0)

        new_id = self.repo.add(SAMPLE_NEWS_1)

        self.assertIsNotNone(new_id)
        self.assertEqual(self._get_row_count(), 1)
        # ID check depends on whether previous tests ran and cleared sequence
        self.assertEqual(new_id, 1)  # Less reliable across test runs

        # Verify content (optional but good)
        retrieved = self.repo.get_by_id(new_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["title"], SAMPLE_NEWS_1["title"])
        self.assertEqual(retrieved["link"], SAMPLE_NEWS_1["link"])
        self.assertEqual(retrieved["summary"], SAMPLE_NEWS_1["summary"])

    def test_02_add_single_duplicate_link(self):
        """Test adding a news item with a duplicate link should be skipped."""
        print(f"Running {self._testMethodName}...")
        self._add_sample_news(SAMPLE_NEWS_1)  # Add the first item
        self.assertEqual(self._get_row_count(), 1)

        # Try adding again with the same link
        new_id_duplicate = self.repo.add(SAMPLE_NEWS_1)

        self.assertIsNone(new_id_duplicate, "Adding duplicate link should return None.")
        self.assertEqual(
            self._get_row_count(), 1, "Row count should not increase for duplicate."
        )

    def test_03_add_single_invalid_data(self):
        """Test adding news items with missing required fields (title/link)."""
        print(f"Running {self._testMethodName}...")
        self.assertEqual(self._get_row_count(), 0)

        id_no_link = self.repo.add(INVALID_NEWS_NO_LINK)
        self.assertIsNone(id_no_link, "Adding item with no link should return None.")
        self.assertEqual(
            self._get_row_count(), 0, "Row count should not increase for invalid item."
        )

        id_no_title = self.repo.add(INVALID_NEWS_NO_TITLE)
        self.assertIsNone(id_no_title, "Adding item with no title should return None.")
        self.assertEqual(
            self._get_row_count(), 0, "Row count should not increase for invalid item."
        )

    def test_04_add_batch_valid(self):
        """Test adding a batch of valid, unique news items."""
        print(f"Running {self._testMethodName}...")
        self.assertEqual(self._get_row_count(), 0)
        batch_items = [SAMPLE_NEWS_1, SAMPLE_NEWS_2, SAMPLE_NEWS_3]

        added_count, skipped_count = self.repo.add_batch(batch_items)

        self.assertEqual(added_count, 3, "Should add all 3 valid items.")
        self.assertEqual(skipped_count, 0, "Should skip 0 items.")
        self.assertEqual(
            self._get_row_count(), 3, "Row count should be 3 after batch add."
        )

        # Verify one item (optional)
        # Need to get ID reliably - let's retrieve by link instead
        retrieved = self.repo.get_all(limit=10)  # Get all and find the one we want
        found = next(
            (item for item in retrieved if item["link"] == SAMPLE_NEWS_2["link"]), None
        )
        self.assertIsNotNone(found)
        self.assertEqual(found["link"], SAMPLE_NEWS_2["link"])

    def test_05_add_batch_with_duplicates_in_batch(self):
        """Test adding a batch where some items are duplicates within the batch itself."""
        print(f"Running {self._testMethodName}...")
        self.assertEqual(self._get_row_count(), 0)
        batch_items = [SAMPLE_NEWS_1, SAMPLE_NEWS_2, SAMPLE_NEWS_1]  # Duplicate NEWS_1

        added_count, skipped_count = self.repo.add_batch(batch_items)

        # The implementation should handle duplicates within the batch
        self.assertEqual(added_count, 2, "Should add only 2 unique items.")
        self.assertEqual(skipped_count, 1, "Should skip 1 duplicate item.")
        self.assertEqual(self._get_row_count(), 2, "Row count should be 2.")

    def test_06_add_batch_with_existing_in_db(self):
        """Test adding a batch where some items already exist in the database."""
        print(f"Running {self._testMethodName}...")
        self._add_sample_news(SAMPLE_NEWS_1)  # Pre-populate DB
        self.assertEqual(self._get_row_count(), 1)

        batch_items = [SAMPLE_NEWS_1, SAMPLE_NEWS_2, SAMPLE_NEWS_3]  # NEWS_1 exists

        added_count, skipped_count = self.repo.add_batch(batch_items)

        self.assertEqual(added_count, 2, "Should add only the 2 new items.")
        self.assertEqual(skipped_count, 1, "Should skip 1 existing item.")
        self.assertEqual(
            self._get_row_count(), 3, "Row count should be 3 (1 existing + 2 new)."
        )

    def test_07_add_batch_with_invalid(self):
        """Test adding a batch containing invalid items."""
        print(f"Running {self._testMethodName}...")
        batch_items = [SAMPLE_NEWS_1, INVALID_NEWS_NO_LINK, SAMPLE_NEWS_2]

        added_count, skipped_count = self.repo.add_batch(batch_items)

        self.assertEqual(added_count, 2, "Should add 2 valid items.")
        self.assertEqual(skipped_count, 1, "Should skip 1 invalid item.")
        self.assertEqual(self._get_row_count(), 2, "Row count should be 2.")

    def test_08_add_batch_empty(self):
        """Test adding an empty batch."""
        print(f"Running {self._testMethodName}...")
        added_count, skipped_count = self.repo.add_batch([])
        self.assertEqual(added_count, 0)
        self.assertEqual(skipped_count, 0)
        self.assertEqual(self._get_row_count(), 0)

    def test_09_get_by_id(self):
        """Test retrieving a news item by its ID."""
        print(f"Running {self._testMethodName}...")
        id1 = self._add_sample_news(SAMPLE_NEWS_1)
        id2 = self._add_sample_news(SAMPLE_NEWS_2)

        retrieved1 = self.repo.get_by_id(id1)
        self.assertIsNotNone(retrieved1)
        self.assertEqual(retrieved1["id"], id1)
        self.assertEqual(retrieved1["link"], SAMPLE_NEWS_1["link"])

        retrieved2 = self.repo.get_by_id(id2)
        self.assertIsNotNone(retrieved2)
        self.assertEqual(retrieved2["id"], id2)
        self.assertEqual(retrieved2["link"], SAMPLE_NEWS_2["link"])

        non_existent = self.repo.get_by_id(999)
        self.assertIsNone(non_existent, "Getting non-existent ID should return None.")

    def test_10_get_all(self):
        """Test retrieving all news items with pagination."""
        print(f"Running {self._testMethodName}...")
        id3 = self._add_sample_news(SAMPLE_NEWS_3)  # Date: 12:00
        id2 = self._add_sample_news(SAMPLE_NEWS_2)  # Date: 11:00
        id1 = self._add_sample_news(SAMPLE_NEWS_1)  # Date: 10:00

        all_news = self.repo.get_all(limit=10)
        self.assertEqual(len(all_news), 3)
        # Check order (DESC date, DESC id)
        self.assertEqual(all_news[0]["id"], id3)
        self.assertEqual(all_news[1]["id"], id2)
        self.assertEqual(all_news[2]["id"], id1)

        # Test limit
        limited_news = self.repo.get_all(limit=2)
        self.assertEqual(len(limited_news), 2)
        self.assertEqual(limited_news[0]["id"], id3)
        self.assertEqual(limited_news[1]["id"], id2)

        # Test offset
        offset_news = self.repo.get_all(limit=2, offset=1)
        self.assertEqual(len(offset_news), 2)
        self.assertEqual(offset_news[0]["id"], id2)
        self.assertEqual(offset_news[1]["id"], id1)

        # Test empty table
        self.assertTrue(self.repo.clear_all())  # Use clear_all to empty
        empty_news = self.repo.get_all()
        self.assertEqual(len(empty_news), 0)

    def test_11_delete(self):
        """Test deleting a news item."""
        print(f"Running {self._testMethodName}...")
        id1 = self._add_sample_news(SAMPLE_NEWS_1)
        id2 = self._add_sample_news(SAMPLE_NEWS_2)
        self.assertEqual(self._get_row_count(), 2)

        deleted = self.repo.delete(id1)
        self.assertTrue(deleted, "Delete existing item should return True.")
        self.assertEqual(
            self._get_row_count(), 1, "Row count should decrease after delete."
        )
        self.assertIsNone(
            self.repo.get_by_id(id1), "Deleted item should not be retrievable."
        )

        not_deleted = self.repo.delete(999)
        self.assertFalse(not_deleted, "Deleting non-existent ID should return False.")
        self.assertEqual(self._get_row_count(), 1, "Row count should remain unchanged.")

    def test_12_exists_by_link(self):
        """Test checking for news existence by link."""
        print(f"Running {self._testMethodName}...")
        self._add_sample_news(SAMPLE_NEWS_1)

        self.assertTrue(self.repo.exists_by_link(SAMPLE_NEWS_1["link"]))
        self.assertFalse(self.repo.exists_by_link("http://does.not.exist/link"))

    def test_13_get_all_links(self):
        """Test retrieving all unique links."""
        print(f"Running {self._testMethodName}...")
        self._add_sample_news(SAMPLE_NEWS_1)
        self._add_sample_news(SAMPLE_NEWS_2)

        links = self.repo.get_all_links()
        self.assertIsInstance(links, list)
        self.assertEqual(len(links), 2)
        self.assertIn(SAMPLE_NEWS_1["link"], links)
        self.assertIn(SAMPLE_NEWS_2["link"], links)

        # Test empty
        self.assertTrue(self.repo.clear_all())
        empty_links = self.repo.get_all_links()
        self.assertEqual(len(empty_links), 0)

    def test_14_clear_all(self):
        """Test clearing all news items."""
        print(f"Running {self._testMethodName}...")
        self._add_sample_news(SAMPLE_NEWS_1)
        self._add_sample_news(SAMPLE_NEWS_2)
        self.assertEqual(self._get_row_count(), 2)

        cleared = self.repo.clear_all()
        self.assertTrue(cleared, "clear_all should return True on success.")
        self.assertEqual(
            self._get_row_count(), 0, "Row count should be 0 after clear_all."
        )

        # Test clearing already empty table
        cleared_again = self.repo.clear_all()
        self.assertTrue(cleared_again)
        self.assertEqual(self._get_row_count(), 0)


if __name__ == "__main__":
    print("Starting NewsRepository tests...")
    unittest.main()
