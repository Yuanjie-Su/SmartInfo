# tests/test_db/test_source_repository.py
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
from src.db.repositories import NewsSourceRepository, NewsCategoryRepository
from src.db.schema_constants import NEWS_SOURCES_TABLE, NEWS_CATEGORY_TABLE

# Ensure a QApplication instance exists if QSql requires it (important for testing)
_app = QApplication.instance() or QApplication([])

# --- Test Data for Sources ---
SAMPLE_SOURCE_1 = {
    "name": "科技日报",
    "url": "http://tech.example.com",
    "category_id": 1,
}
SAMPLE_SOURCE_2 = {
    "name": "商业晨报",
    "url": "http://business.example.com",
    "category_id": 2,
}
SAMPLE_SOURCE_3 = {
    "name": "国际新闻网",
    "url": "http://international.example.com",
    "category_id": 3,
}
INVALID_SOURCE_NO_URL = {"name": "无效来源", "category_id": 1}
INVALID_SOURCE_NO_NAME = {"url": "http://noname.example.com", "category_id": 1}

# --- Sample Category Names ---
CATEGORY_TECH = "技术"
CATEGORY_BUSINESS = "商业"
CATEGORY_INTERNATIONAL = "国际"


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


class TestSourceRepository(unittest.TestCase):
    """Test suite for the NewsSourceRepository class."""

    db_manager: DatabaseConnectionManager
    db: QSqlDatabase
    repo: NewsSourceRepository
    category_repo: NewsCategoryRepository
    db_fd = None  # File descriptor for temp file
    db_path = None  # Path to temp file
    _original_global_config = None  # To store original config

    # Category IDs that will be populated in setUpClass
    category_ids = {}

    @classmethod
    def setUpClass(cls):
        """Set up for all tests in this class (runs once)."""
        print("setUpClass: Setting up temporary database...")

        # 1. Create temporary DB file
        cls.db_fd, cls.db_path = tempfile.mkstemp(
            suffix=".db", prefix="test_source_repo_"
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

        # 5. Create the repository instances *after* DB is set up
        cls.repo = NewsSourceRepository()
        cls.category_repo = NewsCategoryRepository()
        print("setUpClass: Repository instances created.")

        # 6. Create categories needed for tests
        try:
            print("setUpClass: Creating test categories...")
            cls.category_ids[CATEGORY_TECH] = cls.category_repo.add(CATEGORY_TECH)
            cls.category_ids[CATEGORY_BUSINESS] = cls.category_repo.add(
                CATEGORY_BUSINESS
            )
            cls.category_ids[CATEGORY_INTERNATIONAL] = cls.category_repo.add(
                CATEGORY_INTERNATIONAL
            )
            print(f"setUpClass: Created test categories with IDs: {cls.category_ids}")

            # Update sample sources with real category IDs
            SAMPLE_SOURCE_1["category_id"] = cls.category_ids[CATEGORY_TECH]
            SAMPLE_SOURCE_2["category_id"] = cls.category_ids[CATEGORY_BUSINESS]
            SAMPLE_SOURCE_3["category_id"] = cls.category_ids[CATEGORY_INTERNATIONAL]
            INVALID_SOURCE_NO_URL["category_id"] = cls.category_ids[CATEGORY_TECH]
            INVALID_SOURCE_NO_NAME["category_id"] = cls.category_ids[CATEGORY_TECH]
        except Exception as e:
            print(f"Error creating test categories: {e}")
            raise

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
            f"\nsetUp ({self._testMethodName}): Clearing {NEWS_SOURCES_TABLE} table..."
        )
        query = QSqlQuery(self.db)
        if not query.exec(f"DELETE FROM {NEWS_SOURCES_TABLE}"):
            # Use assertFailure for critical setup steps
            self.fail(
                f"setUp ({self._testMethodName}): Failed to clear table: {query.lastError().text()}"
            )
        # Optionally reset sequence (might not be strictly needed for in-memory)
        query.exec(
            f"DELETE FROM sqlite_sequence WHERE name='{NEWS_SOURCES_TABLE}'"
        )  # Ignore errors
        print(f"setUp ({self._testMethodName}): Table cleared.")

    # --- Helper Methods ---
    def _add_sample_source(self, source_data: Dict[str, Any]) -> int:
        """Adds a sample source and returns its ID."""
        new_id = self.repo.add(
            source_data["name"], source_data["url"], source_data["category_id"]
        )
        self.assertIsNotNone(
            new_id, f"Failed to add sample source: {source_data.get('name')}"
        )
        self.assertIsInstance(new_id, int)
        return new_id

    def _get_row_count(self) -> int:
        """Gets the current row count in the news_sources table."""
        query = QSqlQuery(f"SELECT COUNT(*) FROM {NEWS_SOURCES_TABLE}", self.db)
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
    def test_01_add_valid_source(self):
        """Test adding a valid news source."""
        print(f"Running {self._testMethodName}...")
        initial_count = self._get_row_count()
        self.assertEqual(initial_count, 0)

        new_id = self.repo.add(
            SAMPLE_SOURCE_1["name"],
            SAMPLE_SOURCE_1["url"],
            SAMPLE_SOURCE_1["category_id"],
        )

        self.assertIsNotNone(new_id)
        self.assertEqual(self._get_row_count(), 1)
        self.assertEqual(new_id, 1)  # First ID should be 1

        # Verify content
        retrieved = self.repo.get_by_id(new_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved[0], new_id)
        self.assertEqual(retrieved[1], SAMPLE_SOURCE_1["name"])
        self.assertEqual(retrieved[2], SAMPLE_SOURCE_1["url"])
        self.assertEqual(retrieved[3], SAMPLE_SOURCE_1["category_id"])

    def test_02_add_duplicate_url(self):
        """Test adding a source with a duplicate URL."""
        print(f"Running {self._testMethodName}...")
        # Add first source
        first_id = self._add_sample_source(SAMPLE_SOURCE_1)
        self.assertEqual(self._get_row_count(), 1)

        # Try adding a source with the same URL but different name
        duplicate_source = {
            "name": "Different Name",
            "url": SAMPLE_SOURCE_1["url"],  # Same URL
            "category_id": SAMPLE_SOURCE_1["category_id"],
        }

        second_id = self.repo.add(
            duplicate_source["name"],
            duplicate_source["url"],
            duplicate_source["category_id"],
        )

        # Should return the ID of the existing source
        self.assertEqual(second_id, first_id)
        self.assertEqual(
            self._get_row_count(), 1, "Row count should not increase for duplicate URL."
        )

    def test_03_add_invalid_source(self):
        """Test adding sources with missing required fields."""
        print(f"Running {self._testMethodName}...")
        self.assertEqual(self._get_row_count(), 0)

        # Test source with no URL (should fail)
        if "url" not in INVALID_SOURCE_NO_URL:
            no_url_id = self.repo.add(
                INVALID_SOURCE_NO_URL["name"], "", INVALID_SOURCE_NO_URL["category_id"]
            )
            self.assertIsNone(no_url_id, "Adding source with no URL should return None")
            self.assertEqual(self._get_row_count(), 0)

        # Test source with no name (should fail)
        if "name" not in INVALID_SOURCE_NO_NAME:
            no_name_id = self.repo.add(
                "", INVALID_SOURCE_NO_NAME["url"], INVALID_SOURCE_NO_NAME["category_id"]
            )
            self.assertIsNone(
                no_name_id, "Adding source with no name should return None"
            )
            self.assertEqual(self._get_row_count(), 0)

    def test_04_get_by_id(self):
        """Test retrieving a source by ID."""
        print(f"Running {self._testMethodName}...")
        id1 = self._add_sample_source(SAMPLE_SOURCE_1)
        id2 = self._add_sample_source(SAMPLE_SOURCE_2)

        # Retrieve and verify first source
        source1 = self.repo.get_by_id(id1)
        self.assertIsNotNone(source1)
        self.assertEqual(source1[0], id1)
        self.assertEqual(source1[1], SAMPLE_SOURCE_1["name"])
        self.assertEqual(source1[2], SAMPLE_SOURCE_1["url"])
        self.assertEqual(source1[3], SAMPLE_SOURCE_1["category_id"])

        # Retrieve and verify second source
        source2 = self.repo.get_by_id(id2)
        self.assertIsNotNone(source2)
        self.assertEqual(source2[0], id2)
        self.assertEqual(source2[1], SAMPLE_SOURCE_2["name"])
        self.assertEqual(source2[2], SAMPLE_SOURCE_2["url"])
        self.assertEqual(source2[3], SAMPLE_SOURCE_2["category_id"])

        # Test non-existent ID
        non_existent = self.repo.get_by_id(999)
        self.assertIsNone(non_existent)

    def test_05_get_by_url(self):
        """Test retrieving a source by URL."""
        print(f"Running {self._testMethodName}...")
        id1 = self._add_sample_source(SAMPLE_SOURCE_1)

        # Retrieve and verify by URL
        source = self.repo.get_by_url(SAMPLE_SOURCE_1["url"])
        self.assertIsNotNone(source)
        self.assertEqual(source[0], id1)
        self.assertEqual(source[1], SAMPLE_SOURCE_1["name"])
        self.assertEqual(source[2], SAMPLE_SOURCE_1["url"])

        # Test non-existent URL
        non_existent = self.repo.get_by_url("http://non-existent.example.com")
        self.assertIsNone(non_existent)

    def test_06_get_all(self):
        """Test retrieving all sources."""
        print(f"Running {self._testMethodName}...")
        # Add sample sources
        id1 = self._add_sample_source(SAMPLE_SOURCE_1)
        id2 = self._add_sample_source(SAMPLE_SOURCE_2)
        id3 = self._add_sample_source(SAMPLE_SOURCE_3)

        # Get all sources
        all_sources = self.repo.get_all()

        # Verify count and content
        self.assertEqual(len(all_sources), 3)

        # Verify each source exists in the results
        source_names = [src[1] for src in all_sources]
        source_urls = [src[2] for src in all_sources]
        source_ids = [src[0] for src in all_sources]

        self.assertIn(SAMPLE_SOURCE_1["name"], source_names)
        self.assertIn(SAMPLE_SOURCE_2["name"], source_names)
        self.assertIn(SAMPLE_SOURCE_3["name"], source_names)
        self.assertIn(SAMPLE_SOURCE_1["url"], source_urls)
        self.assertIn(SAMPLE_SOURCE_2["url"], source_urls)
        self.assertIn(SAMPLE_SOURCE_3["url"], source_urls)
        self.assertIn(id1, source_ids)
        self.assertIn(id2, source_ids)
        self.assertIn(id3, source_ids)

        # Each result should have 5 elements: id, name, url, category_id, category_name
        for src in all_sources:
            self.assertEqual(len(src), 5)

    def test_07_get_by_category(self):
        """Test retrieving sources by category."""
        print(f"Running {self._testMethodName}...")
        # Add sample sources
        self._add_sample_source(SAMPLE_SOURCE_1)  # Tech category
        self._add_sample_source(SAMPLE_SOURCE_2)  # Business category
        self._add_sample_source(SAMPLE_SOURCE_3)  # International category

        # Get sources for tech category
        tech_sources = self.repo.get_by_category(SAMPLE_SOURCE_1["category_id"])

        # Should have only one source in tech category
        self.assertEqual(len(tech_sources), 1)
        self.assertEqual(tech_sources[0][1], SAMPLE_SOURCE_1["name"])
        self.assertEqual(tech_sources[0][2], SAMPLE_SOURCE_1["url"])

        # Get sources for business category
        business_sources = self.repo.get_by_category(SAMPLE_SOURCE_2["category_id"])

        # Should have only one source in business category
        self.assertEqual(len(business_sources), 1)
        self.assertEqual(business_sources[0][1], SAMPLE_SOURCE_2["name"])
        self.assertEqual(business_sources[0][2], SAMPLE_SOURCE_2["url"])

        # Test non-existent category
        non_existent_category = self.repo.get_by_category(999)
        self.assertEqual(len(non_existent_category), 0)

    def test_08_update(self):
        """Test updating a source."""
        print(f"Running {self._testMethodName}...")
        # Add a source
        id1 = self._add_sample_source(SAMPLE_SOURCE_1)

        # Update the source
        NEW_NAME = "Updated Source Name"
        NEW_URL = "http://updated.example.com"
        NEW_CATEGORY_ID = SAMPLE_SOURCE_2["category_id"]  # Change to business category

        updated = self.repo.update(id1, NEW_NAME, NEW_URL, NEW_CATEGORY_ID)

        # Verify update was successful
        self.assertTrue(updated)

        # Verify new values in database
        source = self.repo.get_by_id(id1)
        self.assertEqual(source[1], NEW_NAME)
        self.assertEqual(source[2], NEW_URL)
        self.assertEqual(source[3], NEW_CATEGORY_ID)

        # Test updating non-existent source
        non_existent_update = self.repo.update(
            999, "Non-existent", "http://non-existent.com", 1
        )
        self.assertFalse(non_existent_update)

    def test_09_delete(self):
        """Test deleting a source."""
        print(f"Running {self._testMethodName}...")
        # Add sample sources
        id1 = self._add_sample_source(SAMPLE_SOURCE_1)
        id2 = self._add_sample_source(SAMPLE_SOURCE_2)
        self.assertEqual(self._get_row_count(), 2)

        # Delete one source
        deleted = self.repo.delete(id1)

        # Verify deletion was successful
        self.assertTrue(deleted)
        self.assertEqual(self._get_row_count(), 1)

        # Verify the source is no longer retrievable
        source = self.repo.get_by_id(id1)
        self.assertIsNone(source)

        # But other source still exists
        source2 = self.repo.get_by_id(id2)
        self.assertIsNotNone(source2)

        # Test deleting non-existent source
        non_existent_delete = self.repo.delete(999)
        self.assertFalse(non_existent_delete)
        self.assertEqual(self._get_row_count(), 1)

    def test_10_delete_all(self):
        """Test deleting all sources."""
        print(f"Running {self._testMethodName}...")
        # Add sample sources
        self._add_sample_source(SAMPLE_SOURCE_1)
        self._add_sample_source(SAMPLE_SOURCE_2)
        self._add_sample_source(SAMPLE_SOURCE_3)
        self.assertEqual(self._get_row_count(), 3)

        # Delete all sources
        all_deleted = self.repo.delete_all()

        # Verify all sources were deleted
        self.assertTrue(all_deleted)
        self.assertEqual(self._get_row_count(), 0)

        # Test deleting from empty table
        empty_delete = self.repo.delete_all()
        self.assertTrue(empty_delete)


if __name__ == "__main__":
    print("Starting NewsSourceRepository tests...")
    unittest.main()
