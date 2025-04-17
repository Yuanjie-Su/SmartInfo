# tests/test_db/test_category_repository.py
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
from src.db.repositories import NewsCategoryRepository
from src.db.schema_constants import NEWS_CATEGORY_TABLE

# Ensure a QApplication instance exists if QSql requires it (important for testing)
_app = QApplication.instance() or QApplication([])

# --- Test Data for Categories ---
SAMPLE_CATEGORY_1 = "技术新闻"
SAMPLE_CATEGORY_2 = "商业新闻"
SAMPLE_CATEGORY_3 = "国际新闻"
INVALID_CATEGORY = ""  # 假设空名称是无效的


# --- Mock AppConfig (Adapted from test_connection.py) ---
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


class TestCategoryRepository(unittest.TestCase):
    """Test suite for the NewsCategoryRepository class."""

    db_manager: DatabaseConnectionManager
    db: QSqlDatabase
    repo: NewsCategoryRepository
    db_fd = None  # File descriptor for temp file
    db_path = None  # Path to temp file
    _original_global_config = None  # To store original config

    @classmethod
    def setUpClass(cls):
        """Set up for all tests in this class (runs once)."""
        print("setUpClass: Setting up temporary database...")

        # 1. Create temporary DB file
        cls.db_fd, cls.db_path = tempfile.mkstemp(
            suffix=".db", prefix="test_category_repo_"
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
        cls.repo = NewsCategoryRepository()
        print("setUpClass: NewsCategoryRepository instance created.")

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
            f"\nsetUp ({self._testMethodName}): Clearing {NEWS_CATEGORY_TABLE} table..."
        )
        query = QSqlQuery(self.db)
        if not query.exec(f"DELETE FROM {NEWS_CATEGORY_TABLE}"):
            # Use assertFailure for critical setup steps
            self.fail(
                f"setUp ({self._testMethodName}): Failed to clear table: {query.lastError().text()}"
            )
        # Optionally reset sequence (might not be strictly needed for in-memory)
        query.exec(
            f"DELETE FROM sqlite_sequence WHERE name='{NEWS_CATEGORY_TABLE}'"
        )  # Ignore errors
        print(f"setUp ({self._testMethodName}): Table cleared.")

    # --- Helper Methods ---
    def _add_sample_category(self, name: str) -> int:
        """Adds a sample category and returns its ID."""
        new_id = self.repo.add(name)
        self.assertIsNotNone(new_id, f"Failed to add sample category: {name}")
        self.assertIsInstance(new_id, int)
        return new_id

    def _get_row_count(self) -> int:
        """Gets the current row count in the news_category table."""
        query = QSqlQuery(f"SELECT COUNT(*) FROM {NEWS_CATEGORY_TABLE}", self.db)
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
    def test_01_add_valid_category(self):
        """Test adding a valid category."""
        print(f"Running {self._testMethodName}...")
        initial_count = self._get_row_count()
        self.assertEqual(initial_count, 0)

        new_id = self.repo.add(SAMPLE_CATEGORY_1)

        self.assertIsNotNone(new_id)
        self.assertEqual(self._get_row_count(), 1)
        self.assertEqual(new_id, 1)  # First ID should be 1

        # Verify content
        retrieved = self.repo.get_by_id(new_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved[0], new_id)
        self.assertEqual(retrieved[1], SAMPLE_CATEGORY_1)

    def test_02_add_duplicate_category(self):
        """Test adding a duplicate category."""
        print(f"Running {self._testMethodName}...")
        # Add first category
        first_id = self._add_sample_category(SAMPLE_CATEGORY_1)
        self.assertEqual(self._get_row_count(), 1)

        # Try adding the same category again
        second_id = self.repo.add(SAMPLE_CATEGORY_1)

        # Should return the ID of the existing category, not create a new one
        self.assertEqual(second_id, first_id)
        self.assertEqual(
            self._get_row_count(), 1, "Row count should not increase for duplicate."
        )

    def test_03_add_invalid_category(self):
        """Test adding an invalid category (empty name)."""
        print(f"Running {self._testMethodName}...")
        self.assertEqual(self._get_row_count(), 0)

        new_id = self.repo.add(INVALID_CATEGORY)

        # Implementation specific: might return None or raise error
        self.assertIsNone(new_id, "Adding invalid category should return None")
        self.assertEqual(
            self._get_row_count(), 0, "Row count should not change for invalid category"
        )

    def test_04_get_by_id(self):
        """Test retrieving a category by ID."""
        print(f"Running {self._testMethodName}...")
        id1 = self._add_sample_category(SAMPLE_CATEGORY_1)
        id2 = self._add_sample_category(SAMPLE_CATEGORY_2)

        # Retrieve and verify first category
        cat1 = self.repo.get_by_id(id1)
        self.assertIsNotNone(cat1)
        self.assertEqual(cat1[0], id1)
        self.assertEqual(cat1[1], SAMPLE_CATEGORY_1)

        # Retrieve and verify second category
        cat2 = self.repo.get_by_id(id2)
        self.assertIsNotNone(cat2)
        self.assertEqual(cat2[0], id2)
        self.assertEqual(cat2[1], SAMPLE_CATEGORY_2)

        # Test non-existent ID
        non_existent = self.repo.get_by_id(999)
        self.assertIsNone(non_existent)

    def test_05_get_by_name(self):
        """Test retrieving a category by name."""
        print(f"Running {self._testMethodName}...")
        id1 = self._add_sample_category(SAMPLE_CATEGORY_1)

        # Retrieve and verify by name
        cat = self.repo.get_by_name(SAMPLE_CATEGORY_1)
        self.assertIsNotNone(cat)
        self.assertEqual(cat[0], id1)
        self.assertEqual(cat[1], SAMPLE_CATEGORY_1)

        # Test non-existent name
        non_existent = self.repo.get_by_name("Non-existent Category")
        self.assertIsNone(non_existent)

    def test_06_get_all(self):
        """Test retrieving all categories."""
        print(f"Running {self._testMethodName}...")
        # Add sample categories
        id1 = self._add_sample_category(SAMPLE_CATEGORY_1)
        id2 = self._add_sample_category(SAMPLE_CATEGORY_2)
        id3 = self._add_sample_category(SAMPLE_CATEGORY_3)

        # Get all categories
        all_categories = self.repo.get_all()

        # Verify count and content
        self.assertEqual(len(all_categories), 3)

        # Verify each category exists in the results
        category_names = [cat[1] for cat in all_categories]
        category_ids = [cat[0] for cat in all_categories]

        self.assertIn(SAMPLE_CATEGORY_1, category_names)
        self.assertIn(SAMPLE_CATEGORY_2, category_names)
        self.assertIn(SAMPLE_CATEGORY_3, category_names)
        self.assertIn(id1, category_ids)
        self.assertIn(id2, category_ids)
        self.assertIn(id3, category_ids)

    def test_07_update(self):
        """Test updating a category name."""
        print(f"Running {self._testMethodName}...")
        # Add a category
        id1 = self._add_sample_category(SAMPLE_CATEGORY_1)

        # Update the category name
        NEW_NAME = "Updated Category Name"
        updated = self.repo.update(id1, NEW_NAME)

        # Verify update was successful
        self.assertTrue(updated)

        # Verify new name in database
        cat = self.repo.get_by_id(id1)
        self.assertEqual(cat[1], NEW_NAME)

        # Test updating non-existent category
        non_existent_update = self.repo.update(999, "Non-existent")
        self.assertFalse(non_existent_update)

    def test_08_delete(self):
        """Test deleting a category."""
        print(f"Running {self._testMethodName}...")
        # Add sample categories
        id1 = self._add_sample_category(SAMPLE_CATEGORY_1)
        id2 = self._add_sample_category(SAMPLE_CATEGORY_2)
        self.assertEqual(self._get_row_count(), 2)

        # Delete one category
        deleted = self.repo.delete(id1)

        # Verify deletion was successful
        self.assertTrue(deleted)
        self.assertEqual(self._get_row_count(), 1)

        # Verify the category is no longer retrievable
        cat = self.repo.get_by_id(id1)
        self.assertIsNone(cat)

        # But other category still exists
        cat2 = self.repo.get_by_id(id2)
        self.assertIsNotNone(cat2)

        # Test deleting non-existent category
        non_existent_delete = self.repo.delete(999)
        self.assertFalse(non_existent_delete)
        self.assertEqual(self._get_row_count(), 1)

    def test_09_delete_all(self):
        """Test deleting all categories."""
        print(f"Running {self._testMethodName}...")
        # Add sample categories
        self._add_sample_category(SAMPLE_CATEGORY_1)
        self._add_sample_category(SAMPLE_CATEGORY_2)
        self._add_sample_category(SAMPLE_CATEGORY_3)
        self.assertEqual(self._get_row_count(), 3)

        # Delete all categories
        all_deleted = self.repo.delete_all()

        # Verify all categories were deleted
        self.assertTrue(all_deleted)
        self.assertEqual(self._get_row_count(), 0)

        # Test deleting from empty table
        empty_delete = self.repo.delete_all()
        self.assertTrue(empty_delete)

    def test_10_get_with_source_count(self):
        """Test getting categories with source count (if available)."""
        print(f"Running {self._testMethodName}...")
        # Add sample categories
        id1 = self._add_sample_category(SAMPLE_CATEGORY_1)
        id2 = self._add_sample_category(SAMPLE_CATEGORY_2)

        # Get categories with source count
        categories_with_count = self.repo.get_with_source_count()

        # Verify results
        self.assertEqual(len(categories_with_count), 2)

        # Each result should have 3 elements: id, name, count
        for cat in categories_with_count:
            self.assertEqual(len(cat), 3)
            # Source count should be 0 since we haven't added any sources
            self.assertEqual(cat[2], 0)


if __name__ == "__main__":
    print("Starting NewsCategoryRepository tests...")
    unittest.main()
