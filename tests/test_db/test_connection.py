# tests/test_db/test_connection.py (Corrected)
import unittest
import os
import sys
import tempfile
import time

# --- Adjust sys.path to find src ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(
    os.path.dirname(current_dir)
)  # Adjust based on your test dir location
if project_root not in sys.path:
    sys.path.insert(0, project_root)
# ------------------------------------

from PySide6.QtWidgets import QApplication
from PySide6.QtSql import QSqlDatabase, QSqlQuery

# --- Import the config module itself ---
import src.config

# Modules to test/use
# We'll access _global_config via src.config module now
from src.config import AppConfig, init_config
from src.db.connection import (
    DatabaseConnectionManager,
    init_db_connection,
    get_db,
    get_db_connection_manager,
    MAIN_DB_CONNECTION_NAME,
)
from src.db.schema_constants import (
    NEWS_CATEGORY_TABLE,
    NEWS_SOURCES_TABLE,
    NEWS_TABLE,
    API_CONFIG_TABLE,
    SYSTEM_CONFIG_TABLE,
    QA_HISTORY_TABLE,
)


# Mock AppConfig (remains the same)
class MockConfig(AppConfig):
    def __init__(self, db_path):
        self._persistent_config = self.DEFAULT_PERSISTENT_CONFIG.copy()
        self._secrets = {}
        self._data_dir = os.path.dirname(db_path)
        self._db_path = db_path
        print(f"MockConfig initialized with DB path: {self._db_path}")

    def _load_secrets_from_env(self):
        pass

    def _ensure_data_dir(self):
        pass

    def _load_from_db(self):
        pass

    def save_persistent(self) -> bool:
        return True


class TestDatabaseConnection(unittest.TestCase):
    app = None
    db_manager = None
    db_handle = None
    db_fd = None
    db_path = None
    _original_global_config = None  # Store the original config object

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            print("Creating QApplication for Connection tests...")
            cls.app = QApplication(sys.argv)

        cls.db_fd, cls.db_path = tempfile.mkstemp(suffix=".db", prefix="test_conn_")
        print(f"Created temporary database for Connection tests: {cls.db_path}")

        # --- Corrected Config Mocking ---
        # 1. Store the original global config object using module reference
        cls._original_global_config = src.config._global_config

        # 2. Create the mock config instance
        mock_config = MockConfig(cls.db_path)

        # 3. Directly assign the mock instance to the module's global variable
        #    This replaces the singleton instance for the duration of this test class.
        src.config._global_config = mock_config
        print(
            f"Overrode global config with MockConfig. DB path: {src.config.get_config().db_path}"
        )
        # --- End Corrected Config Mocking ---

        try:
            print("Initializing DB Connection Manager for Connection tests...")
            # Reset the manager singleton for this test class (uses the mocked global config now)
            DatabaseConnectionManager._instance = None
            cls.db_manager = init_db_connection()
            cls.db_handle = get_db()
            print("DB Connection Manager Initialized for Connection tests.")
        except Exception as e:
            print(f"FATAL: Error during Connection test DB setup: {e}", file=sys.stderr)
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
            # Restore original config before failing
            src.config._global_config = cls._original_global_config
            raise

    @classmethod
    def tearDownClass(cls):
        print("Tearing down Connection test class...")
        if cls.db_manager:
            print("Cleaning up DB Connection Manager...")
            cls.db_manager._cleanup()
            if QSqlDatabase.contains(MAIN_DB_CONNECTION_NAME):
                print(
                    f"Warning: Connection {MAIN_DB_CONNECTION_NAME} still exists after cleanup."
                )
                QSqlDatabase.removeDatabase(MAIN_DB_CONNECTION_NAME)

        if cls.db_fd:
            os.close(cls.db_fd)
        if cls.db_path and os.path.exists(cls.db_path):
            print(f"Deleting temporary database: {cls.db_path}")
            # Add robust deletion
            for _ in range(3):  # Try a few times
                try:
                    os.remove(cls.db_path)
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

        # Restore original config using module reference
        src.config._global_config = cls._original_global_config
        print("Restored original global config.")

        print("Connection test class teardown complete.")

    # --- Test methods remain the same ---

    def test_singleton_instance(self):
        """Verify that DatabaseConnectionManager is a singleton."""
        print("Running test_singleton_instance...")
        instance1 = get_db_connection_manager()
        instance2 = get_db_connection_manager()
        self.assertIs(
            instance1, instance2, "DatabaseConnectionManager should be a singleton"
        )
        self.assertIs(
            instance1,
            self.db_manager,
            "get_db_connection_manager should return the initialized instance",
        )

    def test_initialization_opens_db(self):
        """Verify the database connection is open after initialization."""
        print("Running test_initialization_opens_db...")
        self.assertTrue(self.db_handle.isValid(), "Database handle should be valid")
        self.assertTrue(self.db_handle.isOpen(), "Database connection should be open")
        # Access db_path via the (mocked) global config instance
        self.assertEqual(
            self.db_handle.databaseName(),
            src.config.get_config().db_path,
            "Database name should match the temporary path",
        )

    def test_get_db_returns_valid_connection(self):
        """Verify get_db() returns the correct, open QSqlDatabase instance."""
        print("Running test_get_db_returns_valid_connection...")
        db = get_db()
        self.assertIsInstance(db, QSqlDatabase, "get_db() should return a QSqlDatabase")
        self.assertTrue(db.isValid(), "Returned DB handle should be valid")
        self.assertTrue(db.isOpen(), "Returned DB handle should be open")
        self.assertIs(
            db,
            self.db_handle,
            "get_db() should return the same handle initialized in setUpClass",
        )
        self.assertEqual(
            db.connectionName(),
            MAIN_DB_CONNECTION_NAME,
            f"Connection name should be {MAIN_DB_CONNECTION_NAME}",
        )

    def test_tables_created(self):
        """Verify that the expected tables are created during initialization."""
        print("Running test_tables_created...")
        expected_tables = {
            NEWS_CATEGORY_TABLE,
            NEWS_SOURCES_TABLE,
            NEWS_TABLE,
            API_CONFIG_TABLE,
            SYSTEM_CONFIG_TABLE,
            QA_HISTORY_TABLE,
            "sqlite_sequence",  # Check for this as well if auto-increment is used
        }

        query = QSqlQuery(
            "SELECT name FROM sqlite_master WHERE type='table';", self.db_handle
        )
        tables_from_query = set()
        if not query.exec():
            self.fail(f"Failed to query sqlite_master: {query.lastError().text()}")
        while query.next():
            tables_from_query.add(query.value(0))

        print(f"Tables found in DB: {tables_from_query}")
        missing_tables = expected_tables - tables_from_query
        self.assertFalse(
            missing_tables, f"Expected tables are missing: {missing_tables}"
        )

    def test_wal_mode_set(self):
        """Verify that PRAGMA journal_mode is set to WAL."""
        print("Running test_wal_mode_set...")
        query = QSqlQuery("PRAGMA journal_mode;", self.db_handle)
        self.assertTrue(
            query.exec(), f"Failed to query journal_mode: {query.lastError().text()}"
        )
        self.assertTrue(query.next(), "Failed to get result for journal_mode query")
        journal_mode = query.value(0).lower()
        self.assertEqual(
            journal_mode, "wal", f"Journal mode should be WAL, but got {journal_mode}"
        )


if __name__ == "__main__":
    print("Starting DB Connection tests...")
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    unittest.main()
