#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News Management Tab
Implements news retrieval, viewing, deletion and editing functionality (using Service Layer)
"""

import logging
import asyncio
from typing import List, Dict, Optional, Tuple, Any

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableView,
    QComboBox,
    QLabel,
    QLineEdit,
    QSplitter,
    QTextEdit,
    QHeaderView,
    QMessageBox,
    QProgressDialog,
    QApplication,
)
from PySide6.QtCore import Qt, QSortFilterProxyModel, Signal, Slot, QThreadPool, QObject
from PySide6.QtGui import QStandardItemModel, QStandardItem

from src.services.news_service import NewsService
from src.ui.async_runner import AsyncTaskRunner

logger = logging.getLogger(__name__)


class NewsTab(QWidget):
    """News Management Tab"""

    # Signal to potentially notify other parts of the UI if needed
    news_data_changed = Signal()

    def __init__(self, news_service: NewsService):
        super().__init__()
        self._news_service = news_service
        self.news_data: Dict[int, Dict[str, Any]] = {}  # Cache for loaded news details
        self.categories_cache: List[Tuple[int, str]] = []  # Cache for categories
        self.sources_cache: List[Dict[str, Any]] = []  # Cache for sources
        self._setup_ui()
        self._load_filters()
        self._load_news()

    def _setup_ui(self):
        """Set up user interface"""
        main_layout = QVBoxLayout(self)

        # --- Toolbar ---
        toolbar_layout = QHBoxLayout()
        main_layout.addLayout(toolbar_layout)

        self.fetch_button = QPushButton("Fetch News")
        self.fetch_button.clicked.connect(self._fetch_news)
        toolbar_layout.addWidget(self.fetch_button)

        toolbar_layout.addWidget(QLabel("Category:"))
        self.category_filter = QComboBox()
        self.category_filter.addItem("All", -1)  # UserData -1 for "All"
        toolbar_layout.addWidget(self.category_filter)

        toolbar_layout.addWidget(QLabel("Source:"))
        self.source_filter = QComboBox()
        self.source_filter.addItem("All", -1)  # UserData -1 for "All"
        toolbar_layout.addWidget(self.source_filter)

        toolbar_layout.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search title, source, summary...")
        toolbar_layout.addWidget(self.search_input)

        # --- Splitter ---
        splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(splitter, 1)

        # --- News Table ---
        self.news_table = QTableView()
        self.news_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.news_table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.news_table.verticalHeader().setVisible(False)
        self.news_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.news_table.setSortingEnabled(True)
        splitter.addWidget(self.news_table)

        # --- Preview Area ---
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 5, 0, 0)
        preview_layout.addWidget(QLabel("News Preview:"))
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        preview_layout.addWidget(self.preview_text)
        splitter.addWidget(preview_widget)

        splitter.setSizes([600, 200])  # Adjust initial sizes

        self._setup_table_model()

        # --- Bottom Toolbar ---
        bottom_toolbar = QHBoxLayout()
        main_layout.addLayout(bottom_toolbar)

        self.edit_button = QPushButton("Edit")
        self.edit_button.clicked.connect(self._edit_news)
        self.edit_button.setEnabled(False)  # TODO: Enable when implemented
        bottom_toolbar.addWidget(self.edit_button)

        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self._delete_news)
        bottom_toolbar.addWidget(self.delete_button)

        # TODO: Implement Send to Analysis
        self.analyze_button = QPushButton("Send to Analysis")
        self.analyze_button.clicked.connect(self._send_to_analysis)
        self.analyze_button.setEnabled(False)  # Disable until implemented
        bottom_toolbar.addWidget(self.analyze_button)

        bottom_toolbar.addStretch()

        self.export_button = QPushButton("Export")
        self.export_button.clicked.connect(self._export_news)
        self.export_button.setEnabled(False)  # Disable until implemented
        bottom_toolbar.addWidget(self.export_button)

        self.refresh_button = QPushButton("Refresh List")
        self.refresh_button.clicked.connect(self._refresh_all)
        bottom_toolbar.addWidget(self.refresh_button)

        # --- Connect Signals ---
        self.category_filter.currentIndexChanged.connect(
            self._on_category_filter_changed
        )  # Use index change
        self.source_filter.currentTextChanged.connect(self._apply_filters)
        self.search_input.textChanged.connect(self._apply_filters)
        self.news_table.selectionModel().selectionChanged.connect(
            self._on_selection_changed
        )

    def _setup_table_model(self):
        """Sets up the QStandardItemModel and QSortFilterProxyModel."""
        self.model = QStandardItemModel(0, 5, self)  # 5 columns
        # Use user-friendly headers
        self.model.setHorizontalHeaderLabels(
            ["Title", "Source", "Category", "Published Date", "Analyzed"]
        )

        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1)

        self.news_table.setModel(self.proxy_model)

    def _refresh_all(self):
        """Refreshes both filters and news list."""
        logger.info("Refreshing filters and news list...")
        self._load_filters()
        self._load_news()

    def _load_news(self):
        """Loads news from the service into the table model."""
        logger.info("Loading news data...")
        try:
            # Clear existing data first
            self.model.removeRows(0, self.model.rowCount())
            self.news_data.clear()
            self.preview_text.clear()

            # Fetch news data using the service (adjust limit as needed)
            news_list = self._news_service.get_all_news(limit=1000)

            logger.info(f"Retrieved {len(news_list)} news items from service.")

            # Populate the model
            for news in news_list:
                news_id = news.get("id")
                if news_id is None:
                    logger.warning(
                        f"Skipping news item without ID: {news.get('title')}"
                    )
                    continue

                self.news_data[news_id] = news  # Cache details

                # Create items for the table row
                title_item = QStandardItem(news.get("title", "N/A"))
                title_item.setEditable(False)
                source_item = QStandardItem(news.get("source_name", "N/A"))
                source_item.setEditable(False)
                category_item = QStandardItem(news.get("category_name", "N/A"))
                category_item.setEditable(False)
                date_item = QStandardItem(news.get("published_date", "N/A"))
                date_item.setEditable(False)
                analyzed_item = QStandardItem("Yes" if news.get("analyzed") else "No")
                analyzed_item.setEditable(False)

                # Store the news ID in the first item for easy retrieval
                title_item.setData(news_id, Qt.ItemDataRole.UserRole)

                self.model.appendRow(
                    [title_item, source_item, category_item, date_item, analyzed_item]
                )

            # Apply current filters after loading
            self._apply_filters()
            logger.info(f"Populated table with {self.model.rowCount()} news items.")
            self.news_data_changed.emit()  # Notify if other components need to know

        except Exception as e:
            logger.error(f"Failed to load news: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to load news list: {str(e)}")

    def _load_filters(self):
        """Load filter options"""
        logger.info("Loading filters...")
        try:
            # --- Load Categories ---
            current_category_id = self.category_filter.currentData()
            self.category_filter.blockSignals(True)
            self.category_filter.clear()
            self.category_filter.addItem("All", -1)

            self.categories_cache = self._news_service.get_all_categories()
            restored_cat_index = 0
            for i, (cat_id, cat_name) in enumerate(self.categories_cache):
                self.category_filter.addItem(cat_name, cat_id)
                if cat_id == current_category_id:
                    restored_cat_index = i + 1

            self.category_filter.setCurrentIndex(restored_cat_index)
            self.category_filter.blockSignals(False)
            logger.info(f"Loaded {len(self.categories_cache)} categories into filter.")

            # --- Load Sources (based on the potentially restored category) ---
            # Trigger the source update manually after populating categories
            self._on_category_filter_changed(restored_cat_index)

        except Exception as e:
            logger.error(f"Failed to load filters: {e}", exc_info=True)
            QMessageBox.warning(self, "Warning", f"Failed to load filter options: {str(e)}")
        finally:
            # Ensure signals are unblocked even if errors occur
            self.category_filter.blockSignals(False)

    def _on_category_filter_changed(self, index):
        """Handle category filter change"""
        category_id = self.category_filter.itemData(index)  # Get ID from UserDataRole
        self._update_source_filter(category_id)
        self._apply_filters()  # Apply filters immediately after category changes

    def _update_source_filter(self, category_id: int):
        """Update source filter options based on the selected category"""
        logger.debug(f"Updating source filter for category ID: {category_id}")
        try:
            current_source_text = (
                self.source_filter.currentText()
            )  # Keep track of current selection

            self.source_filter.blockSignals(True)
            self.source_filter.clear()
            self.source_filter.addItem("All", -1)

            # Get sources from the service
            if category_id == -1:  # "All" categories selected
                self.sources_cache = self._news_service.get_all_sources()
                sources_to_add = sorted(
                    list(set(s["name"] for s in self.sources_cache))
                )  # Unique names, sorted
            else:
                # Get sources for the specific category
                self.sources_cache = self._news_service.get_sources_by_category_id(
                    category_id
                )
                sources_to_add = sorted(
                    s["name"] for s in self.sources_cache
                )  # Already filtered

            self.source_filter.addItems(sources_to_add)

            # Try to restore previous selection
            restored_src_index = self.source_filter.findText(current_source_text)
            if restored_src_index != -1:
                self.source_filter.setCurrentIndex(restored_src_index)
            else:
                self.source_filter.setCurrentIndex(0)  # Default to "All"

            self.source_filter.blockSignals(False)
            logger.debug(
                f"Source filter updated with {self.source_filter.count() - 1} sources."
            )

        except Exception as e:
            logger.error(f"Failed to update source filter: {e}", exc_info=True)
            QMessageBox.warning(self, "Warning", f"Failed to update source filter: {str(e)}")
        finally:
            self.source_filter.blockSignals(False)

    def _fetch_news(self):
        """Fetch news"""
        try:
            # Determine which source IDs to fetch based on filters
            source_ids_to_fetch: Optional[List[int]] = (
                None  # None means fetch all active sources
            )

            selected_category_id = self.category_filter.currentData()
            selected_source_name = self.source_filter.currentText()

            all_sources = (
                self._news_service.get_all_sources()
            )  # Fetch all source details

            if selected_category_id != -1:  # Specific category selected
                filtered_by_cat = [
                    s for s in all_sources if s["category_id"] == selected_category_id
                ]
                if (
                    selected_source_name != "All"
                ):  # Specific source in specific category
                    source_ids_to_fetch = [
                        s["id"]
                        for s in filtered_by_cat
                        if s["name"] == selected_source_name
                    ]
                else:  # All sources in specific category
                    source_ids_to_fetch = [s["id"] for s in filtered_by_cat]
            elif (
                selected_source_name != "All"
            ):  # Specific source across all categories
                source_ids_to_fetch = [
                    s["id"] for s in all_sources if s["name"] == selected_source_name
                ]
            # Else: Both are "All", so source_ids_to_fetch remains None (fetch all)

            if source_ids_to_fetch is not None and not source_ids_to_fetch:
                QMessageBox.information(
                    self, "Notice", "No news sources found based on current filters."
                )
                return

            logger.info(
                f"Starting fetch for source IDs: {source_ids_to_fetch if source_ids_to_fetch else 'All'}"
            )

            self.fetch_button.setEnabled(False)
            # --- Progress Bar Setup ---
            self.progress = QProgressDialog("Fetching news...", "Cancel", 0, 0, self)
            self.progress.setWindowTitle("Fetching News")
            self.progress.setWindowModality(Qt.WindowModality.WindowModal)
            self.progress.setMinimumDuration(0)
            self.progress.setValue(0)
            self.progress.setLabelText("Fetching news... Saved 0 items")
            self._saved_item_count_during_fetch = 0

            fetch_coro = self._news_service.fetch_news_from_sources
            fetch_args = ()
            fetch_kwargs = {
                "source_ids": source_ids_to_fetch,
                # --- Modify callback parameter names and processing functions ---
                "on_item_saved": self._on_item_saved_ui, # Callback when an item is *saved*
                "on_fetch_complete": None, # Completion handled by runner signal
            }

            self.runner = AsyncTaskRunner(fetch_coro, *fetch_args, **fetch_kwargs)
            self.runner.setAutoDelete(True)

            self.runner.signals.finished.connect(self._on_fetch_runner_finished)
            self.runner.signals.error.connect(self._on_fetch_error)
            self.progress.canceled.connect(self.runner.cancel)

            QThreadPool.globalInstance().start(self.runner)
            self.progress.show()

        except Exception as e:
            # ... (error handling) ...
            logger.error(f"Failed to initiate news fetch: {e}", exc_info=True)
            self.fetch_button.setEnabled(True)
            if hasattr(self, "progress") and self.progress:
                self.progress.close()
            QMessageBox.critical(self, "Error", f"Failed to initiate news fetch: {str(e)}")

    @Slot(object)
    def _on_item_saved_ui(self, item_data: Dict):
        """Callback triggered AFTER an item is saved by the service."""
        if (
            hasattr(self, "progress")
            and self.progress
            and not self.progress.wasCanceled()
        ):
            # --- Update progress label and count ---
            self._saved_item_count_during_fetch += 1
            self.progress.setLabelText(f"Fetching news... Saved {self._saved_item_count_during_fetch} items")

            # --- Add new item to table model ---
            try:
                news_id = item_data.get("id")
                if news_id is None:
                    logger.warning("Received saved item callback but ID is missing.")
                    return

                # Add to internal cache if needed (or rely on full refresh later)
                self.news_data[news_id] = item_data

                # Create QStandardItem objects for the new row
                title_item = QStandardItem(item_data.get("title", "N/A"))
                source_item = QStandardItem(item_data.get("source_name", "N/A"))
                category_item = QStandardItem(item_data.get("category_name", "N/A"))
                date_item = QStandardItem(item_data.get("published_date", "N/A"))
                analyzed_item = QStandardItem("Yes" if item_data.get("analyzed") else "No")

                title_item.setData(news_id, Qt.ItemDataRole.UserRole)
                for item in [title_item, source_item, category_item, date_item, analyzed_item]:
                    item.setEditable(False)

                # Append the row to the model
                self.model.appendRow([title_item, source_item, category_item, date_item, analyzed_item])

            except Exception as ui_update_err:
                 logger.error(f"Error updating UI for saved item {item_data.get('id')}: {ui_update_err}", exc_info=True)

            QApplication.processEvents()

    @Slot(object)
    def _on_fetch_runner_finished(self, result):
        """Callback for async fetch completion"""
        if hasattr(self, "progress") and self.progress:
            if self.progress.wasCanceled():
                logger.info("Fetch task cancelled by user.")
                self.fetch_button.setEnabled(True)
                return
            # Set progress to 'complete' state if using determinate range
            # self.progress.setValue(self.progress.maximum())
            self.progress.close()

        total_saved_count = self._saved_item_count_during_fetch # Use the counter updated by the callback
        # result from gather might be different now (sum of counts per task)
        logger.info(f"Async fetch task completed. Total items saved via callbacks: {total_saved_count}")

        self._apply_filters() # Just ensure filtering is up-to-date

        self.fetch_button.setEnabled(True)
        QMessageBox.information(
            self, "Fetch Complete", f"Fetch process completed. Saved {total_saved_count} new items."
        )

    @Slot(Exception)
    def _on_fetch_error(self, error):
        """Callback for async fetch error

        Args:
            error: Captured exception
        """
        if hasattr(self, "progress") and self.progress:
            # Close progress dialog even on error, unless it was cancelled
            if not self.progress.wasCanceled():
                self.progress.close()
            else:
                logger.info("Fetch task cancelled, error signal ignored.")
                self.fetch_button.setEnabled(True)
                return  # Don't show error if user cancelled

        logger.error(f"News fetch task failed: {error}", exc_info=error)
        self.fetch_button.setEnabled(True)
        QMessageBox.critical(self, "Fetch Error", f"Error occurred during news fetch:\n{str(error)}")
        # Optionally refresh list even on error?
        # self._load_news()

    def _delete_news(self):
        """Delete news"""
        selected_indexes = self.news_table.selectionModel().selectedRows()
        if not selected_indexes:
            QMessageBox.warning(self, "Notice", "Please select news to delete first.")
            return

        # Get news ID from the model data
        source_index = self.proxy_model.mapToSource(
            selected_indexes[0]
        )  # Assuming single selection
        news_id = self.model.item(source_index.row(), 0).data(Qt.ItemDataRole.UserRole)
        news_title = self.model.item(
            source_index.row(), 0
        ).text()  # For confirmation message

        if news_id is None:
            QMessageBox.critical(self, "Error", "Cannot get ID of selected news.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete this news?\n\nTitle: {news_title}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                if self._news_service.delete_news(news_id):
                    logger.info(f"Successfully deleted news ID: {news_id}")
                    QMessageBox.information(self, "Success", "News deleted.")
                    self._load_news()  # Refresh the list
                    self._load_filters()  # Might affect counts if sources become unused
                else:
                    logger.error(
                        f"Service reported failure deleting news ID: {news_id}"
                    )
                    QMessageBox.warning(self, "Failed", "Failed to delete news. Check logs.")
            except Exception as e:
                logger.error(f"Error calling delete_news service: {e}", exc_info=True)
                QMessageBox.critical(self, "Error", f"Error deleting news: {str(e)}")

    def _edit_news(self):
        """Edit news"""
        # TODO: Implement edit functionality using service layer
        QMessageBox.information(self, "Notice", "Edit functionality not yet implemented.")

    def _send_to_analysis(self):
        """Send to analysis tab"""
        # TODO: Implement logic to get selected news ID and pass it to AnalysisTab
        # This might involve signals/slots or accessing the parent tab widget.
        selected_indexes = self.news_table.selectionModel().selectedRows()
        if not selected_indexes:
            QMessageBox.warning(self, "Notice", "Please select news to analyze first.")
            return
        source_index = self.proxy_model.mapToSource(selected_indexes[0])
        news_id = self.model.item(source_index.row(), 0).data(Qt.ItemDataRole.UserRole)
        news_title = self.model.item(source_index.row(), 0).text()

        if news_id is not None:
            # Example: Access sibling tab (requires MainWindow reference or signal)
            try:
                main_window = self.window()  # Get parent MainWindow
                if hasattr(main_window, "analysis_tab") and main_window.analysis_tab:
                    # Call a method on analysis_tab to load the item
                    main_window.analysis_tab.load_news_for_analysis(news_id)
                    # Switch to the analysis tab
                    if hasattr(main_window, "tabs"):
                        main_window.tabs.setCurrentWidget(main_window.analysis_tab)
                    QMessageBox.information(
                        self, "Notice", f"News '{news_title}' sent to Analysis tab."
                    )
                else:
                    QMessageBox.warning(self, "Error", "Cannot access Analysis tab.")
            except Exception as e:
                logger.error(f"Error sending news to analysis tab: {e}", exc_info=True)
                QMessageBox.critical(self, "Error", f"Failed to send to analysis: {e}")
        else:
            QMessageBox.warning(self, "Error", "Cannot get ID of selected news.")

    def _export_news(self):
        """Export news"""
        # TODO: Implement export functionality using service layer
        QMessageBox.information(self, "Notice", "Export functionality not yet implemented.")

    def _on_selection_changed(self, selected, deselected):
        """Handle selection change event"""
        indexes = selected.indexes()
        if not indexes:
            self.preview_text.clear()
            return

        # Get the news ID from the selected row (use the proxy model index)
        source_index = self.proxy_model.mapToSource(indexes[0])
        news_id = self.model.item(source_index.row(), 0).data(Qt.ItemDataRole.UserRole)

        if news_id is not None and news_id in self.news_data:
            news = self.news_data[news_id]
            # Format the preview text
            preview_html = f"<h3>{news.get('title', 'N/A')}</h3>"
            preview_html += f"<p><b>Source:</b> {news.get('source_name', 'N/A')}<br>"
            preview_html += f"<b>Category:</b> {news.get('category_name', 'N/A')}<br>"
            date_str = (
                news.get("published_date")
                or news.get("date")
                or news.get("fetched_date", "")
            )
            preview_html += f"<b>Date:</b> {date_str[:19] if date_str else 'N/A'}<br>"  # Show time if available
            link = news.get("link", "#")
            preview_html += f"<b>Link:</b> <a href='{link}'>{link}</a><br>"
            preview_html += (
                f"<b>Analyzed:</b> {'Yes' if news.get('analyzed') else 'No'}</p>"
            )
            preview_html += "<hr>"
            preview_html += f"<b>Summary:</b><p>{news.get('summary', 'No summary')}</p>"  # Use summary if available
            # Optionally show full content or LLM analysis
            llm_analysis = news.get("llm_analysis")
            if llm_analysis:
                preview_html += "<hr>"
                preview_html += f"<p><b>AI Analysis:</b></p><p>{llm_analysis}</p>"  # Display LLM analysis

            self.preview_text.setHtml(preview_html)
        else:
            self.preview_text.setText(f"Cannot load preview (ID: {news_id})")

    def _apply_filters(self):
        """Apply the current category, source, and search filters to the proxy model."""
        search_text = self.search_input.text().strip()
        selected_category_text = self.category_filter.currentText()
        selected_source_text = self.source_filter.currentText()

        # Use a custom filter function for more complex filtering
        # Reset any existing regex filter first
        self.proxy_model.setFilterRegularExpression("")
        # Set fixed string for basic text search across all columns
        self.proxy_model.setFilterKeyColumn(-1)  # Search all columns
        self.proxy_model.setFilterFixedString(search_text)

        # Now, apply category and source filtering by hiding/showing rows
        # This is less efficient than using proxy model's filter but simpler for combined filters
        source_model = self.proxy_model.sourceModel()  # Get the QStandardItemModel
        for row in range(source_model.rowCount()):
            category_matches = (
                selected_category_text == "All"
                or source_model.item(row, 2).text() == selected_category_text
            )
            source_matches = (
                selected_source_text == "All"
                or source_model.item(row, 1).text() == selected_source_text
            )

            # Row is visible only if it matches the search text (handled by setFilterFixedString)
            # AND matches the category filter AND matches the source filter.
            # We need to get the visibility status from the proxy model first
            source_index = source_model.index(row, 0)
            proxy_index = self.proxy_model.mapFromSource(source_index)

            # If proxy_index is invalid, it means the row is already filtered out by text search
            text_match = proxy_index.isValid()

            self.news_table.setRowHidden(
                row, not (text_match and category_matches and source_matches)
            )

        logger.debug(
            f"Applied filters: Category='{selected_category_text}', Source='{selected_source_text}', Search='{search_text}'"
        )
