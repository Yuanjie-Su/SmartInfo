#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Main Window Interface Module
Implements the main user interface of the application
"""

import sys
import logging
from typing import Dict, Any, Optional

from PySide6.QtWidgets import (
    QMainWindow,
    QStackedWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStatusBar,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QLabel,
    QFrame,
    QLineEdit,
    QScrollArea,
    QSpacerItem,
)
from PySide6.QtCore import Signal, Slot, Qt

# Import tabs
from .tabs.news_tab import NewsTab
from .tabs.chat_tab import ChatTab
from .settings_window import SettingsWindow
from ..controllers.main_controller import MainController

logger = logging.getLogger(__name__)


class NavigationBar(QWidget):
    page_changed = Signal(int)
    chat_selected = Signal(str)
    new_chat_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NavigationBar")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 10, 5, 10)
        layout.setSpacing(0)

        # 1. Top Function Area
        top_section = QWidget()
        top_layout = QVBoxLayout(top_section)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(5)

        # News Button
        self.news_btn = QPushButton("📰  News")
        self.news_btn.setObjectName("NavBtn_News")
        self.news_btn.setCheckable(True)
        self.news_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.news_btn.setStyleSheet("text-align: left; padding: 8px;")
        self.news_btn.clicked.connect(lambda: self.on_btn_clicked(0))
        top_layout.addWidget(self.news_btn)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setObjectName("NavSeparator")
        separator.setStyleSheet("background-color: #e0e0e0; max-height: 1px;")
        top_layout.addWidget(separator)

        layout.addWidget(top_section)

        # 2. Tool Area
        tools_section = QWidget()
        tools_layout = QVBoxLayout(tools_section)
        tools_layout.setContentsMargins(0, 5, 0, 10)
        tools_layout.setSpacing(8)

        # Tool Container (Horizontal Layout)
        tools_container = QWidget()
        tools_container_layout = QHBoxLayout(tools_container)
        tools_container_layout.setContentsMargins(0, 0, 0, 0)
        tools_container_layout.setSpacing(5)

        # New Chat Button
        self.new_chat_btn = QPushButton("+")
        self.new_chat_btn.setObjectName("NewChatBtn")
        self.new_chat_btn.setToolTip("New Chat")
        self.new_chat_btn.setFixedSize(30, 30)
        self.new_chat_btn.clicked.connect(self._on_new_chat_clicked)
        tools_container_layout.addWidget(self.new_chat_btn)

        # Search Box
        self.search_input = QLineEdit()
        self.search_input.setObjectName("ChatSearchInput")
        self.search_input.setPlaceholderText("Search chats")
        self.search_input.textChanged.connect(self._filter_chats)
        tools_container_layout.addWidget(self.search_input)

        tools_layout.addWidget(tools_container)
        layout.addWidget(tools_section)

        # 3. Chat Record Group Area
        chats_section = QWidget()
        chats_layout = QVBoxLayout(chats_section)
        chats_layout.setContentsMargins(0, 0, 0, 0)
        chats_layout.setSpacing(10)

        # Chat Record Container
        self.chats_container = QWidget()
        self.chats_container_layout = QVBoxLayout(self.chats_container)
        self.chats_container_layout.setContentsMargins(0, 0, 0, 0)
        self.chats_container_layout.setSpacing(1)

        # Add a spacer at the bottom - store reference to it for later management
        self.bottom_spacer = QSpacerItem(
            20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding
        )
        self.chats_container_layout.addItem(self.bottom_spacer)

        # Define the order of groups to ensure consistent display
        self.group_order = ["Today", "Yesterday", "Others"]

        # Create group data structure
        self.groups = {}
        for group_name in self.group_order:
            # Create group label
            label = QLabel(group_name)
            label.setObjectName(f"ChatGroup_{group_name}")
            label.setStyleSheet(
                "font-weight: bold; color: #666; margin-top: 10px; margin-bottom: 2px;"
            )

            # Save to group structure
            self.groups[group_name] = {"label": label, "items": []}

        # Scroll Area
        chats_scroll = QScrollArea()
        chats_scroll.setWidgetResizable(True)
        chats_scroll.setFrameShape(QFrame.NoFrame)
        chats_scroll.setWidget(self.chats_container)
        chats_layout.addWidget(chats_scroll)

        layout.addWidget(chats_section, 1)  # 1 means stretchable

        # 4. Bottom Settings Area
        bottom_section = QWidget()
        bottom_layout = QVBoxLayout(bottom_section)
        bottom_layout.setContentsMargins(0, 10, 0, 5)
        bottom_layout.setSpacing(5)

        # Settings Button
        self.settings_btn = QPushButton("⚙️  Settings")
        self.settings_btn.setObjectName("NavBtn_Settings")
        self.settings_btn.setCheckable(True)
        self.settings_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.settings_btn.setStyleSheet("text-align: left; padding: 8px;")
        self.settings_btn.clicked.connect(lambda: self.on_btn_clicked(2))
        bottom_layout.addWidget(self.settings_btn)

        # Version Information
        version_label = QLabel("v1.0.0")
        version_label.setObjectName("VersionLabel")
        bottom_layout.addWidget(version_label, 0, Qt.AlignmentFlag.AlignHCenter)

        layout.addWidget(bottom_section)

        # Default select News button
        self.news_btn.setChecked(True)

        # Save references to all navigation buttons
        self.nav_buttons = [
            self.news_btn,
            None,
            self.settings_btn,
        ]  # Middle position None will be used to store the current chat button

    def on_btn_clicked(self, idx):
        """Navigation button click handler"""
        # Deselect all buttons
        for btn in [b for b in self.nav_buttons if b is not None]:
            btn.setChecked(False)

        # Set the current button's selected state
        if idx == 0:  # News
            self.news_btn.setChecked(True)
        elif idx == 2:  # Settings
            self.settings_btn.setChecked(True)

        # Emit page change signal
        self.page_changed.emit(idx)

    def _on_new_chat_clicked(self):
        """Create new chat"""
        logger.info("New chat request")
        try:
            # Call the method in MainWindow (this method will call the controller to create a chat and update the UI)
            # The request needs to be passed to MainWindow via signal
            self.new_chat_clicked.emit()
        except Exception as e:
            logger.error(f"Error creating new chat: {e}", exc_info=True)
            # Cannot directly show QMessageBox here because the navigation bar is a child component
            # Error handling will be managed by MainWindow

    def _add_chat_item(self, title, group, chat_id, index=None):
        """Add chat item to the specified group"""
        if group not in self.groups:
            return

        # Create chat button
        chat_btn = QPushButton(title)
        chat_btn.setObjectName(f"ChatBtn_{chat_id}")
        chat_btn.setCheckable(True)
        chat_btn.setStyleSheet(
            "text-align: left; padding: 4px 10px; border-radius: 4px; margin: 0px;"
        )

        # Save chat_id to button's data
        chat_btn.setProperty("chat_id", chat_id)

        # Connect click event
        chat_btn.clicked.connect(lambda: self._on_chat_clicked(chat_btn))

        # First, temporarily remove the bottom spacer to ensure it stays at the bottom
        self.chats_container_layout.removeItem(self.bottom_spacer)

        # Ensure that if the group label has not been added to the layout, it is added
        group_label = self.groups[group]["label"]
        if group_label.parent() != self.chats_container:
            # Need to find the position to insert the group label based on the defined order
            insert_at_index = self.chats_container_layout.count()  # Default to the end

            # Get the current group's index in our expected order
            current_group_index = self.group_order.index(group)

            # Find the next group that is already in the layout according to our order
            for next_group_idx in range(current_group_index + 1, len(self.group_order)):
                next_group = self.group_order[next_group_idx]
                next_group_label = self.groups[next_group]["label"]
                if next_group_label.parent() == self.chats_container:
                    # Found the next group, insert before it
                    insert_at_index = self.chats_container_layout.indexOf(
                        next_group_label
                    )
                    break

            # Insert the group label at the determined position
            self.chats_container_layout.insertWidget(insert_at_index, group_label)
            group_label.show()

        # Determine the insertion position for the chat button
        if index is None:
            # Add to the end of the group (before any next group label)
            label_index = self.chats_container_layout.indexOf(group_label)

            # Find the last button in this group
            last_button_index = label_index
            for i in range(label_index + 1, self.chats_container_layout.count()):
                widget = self.chats_container_layout.itemAt(i).widget()
                # If we find another group label or non-widget item, stop searching
                if widget is None or (
                    isinstance(widget, QLabel)
                    and widget.objectName().startswith("ChatGroup_")
                ):
                    break
                # Otherwise, this is a button in our current group, update the index
                last_button_index = i

            # Insert after the last button in this group
            insert_index = last_button_index + 1
        else:
            # Insert at a specific position within the group
            label_index = self.chats_container_layout.indexOf(group_label)
            if label_index != -1:
                insert_index = label_index + 1 + index
            else:
                # Fallback - this should not happen in our sorting logic
                insert_index = self.chats_container_layout.count()

        # Add the button to the layout at the determined position
        self.chats_container_layout.insertWidget(insert_index, chat_btn)

        # Add the spacer at the end
        self.chats_container_layout.addItem(self.bottom_spacer)

        # Save to group data
        self.groups[group]["items"].append(chat_btn)

        # Automatically select the newly added chat
        self._on_chat_clicked(chat_btn)

    def _on_chat_clicked(self, chat_btn):
        """Chat item click handler"""
        # Deselect all navigation buttons
        for btn in [b for b in self.nav_buttons if b is not None]:
            btn.setChecked(False)

        # Deselect all chat buttons
        for group_data in self.groups.values():
            for btn in group_data["items"]:
                btn.setChecked(False)

        # Set the current chat button to selected state
        chat_btn.setChecked(True)

        # Update the chat button reference in the navigation button array
        self.nav_buttons[1] = chat_btn

        # Get chat_id
        chat_id = chat_btn.property("chat_id")

        # Emit chat selection signal
        self.chat_selected.emit(chat_id)

        # Emit page change signal (index 1 is the QA page)
        self.page_changed.emit(1)

    def _filter_chats(self, keyword):
        """Filter chat items based on keyword"""
        keyword = keyword.lower()

        # Track visibility of each group
        group_has_visible_items = {group: False for group in self.groups}

        # Iterate through all chat buttons, showing or hiding based on title
        for group_name, group_data in self.groups.items():
            for btn in group_data["items"]:
                if keyword:
                    # If there is a keyword, match by title
                    visible = keyword in btn.text().lower()
                    btn.setVisible(visible)
                    if visible:
                        group_has_visible_items[group_name] = True
                else:
                    # If there is no keyword, show all
                    btn.setVisible(True)
                    group_has_visible_items[group_name] = True

        # Update group label visibility based on whether it has visible items
        for group_name, has_visible in group_has_visible_items.items():
            self.groups[group_name]["label"].setVisible(has_visible)

    def update_chat_groups(self, chat_data_list):
        """Update chat groups based on the provided chat data"""
        # First, temporarily remove the bottom spacer
        self.chats_container_layout.removeItem(self.bottom_spacer)

        # Clear existing groups
        for group_data in self.groups.values():
            for btn in group_data["items"]:
                btn.deleteLater()
            group_data["items"] = []

            # If label is already in layout, remove it
            label = group_data["label"]
            if label.parent() == self.chats_container:
                self.chats_container_layout.removeWidget(label)
                label.setParent(None)
                label.hide()

        # Calculate number of chats in each group
        group_counts = {group: 0 for group in self.groups}
        for chat_data in chat_data_list:
            group = chat_data.get("group", "Others")
            if group in group_counts:
                group_counts[group] += 1

        # Add chat items in specified order
        for group_name in self.group_order:
            count = group_counts[group_name]
            # Only add label when group has chat records
            if count > 0:
                group_label = self.groups[group_name]["label"]
                self.chats_container_layout.addWidget(group_label)
                group_label.show()

                # Add all buttons for this group immediately after the label
                group_chats = [
                    data for data in chat_data_list if data.get("group") == group_name
                ]
                for chat_data in group_chats:
                    self._add_chat_item(
                        chat_data["title"], chat_data["group"], chat_data["id"]
                    )

        # Add spacer at the bottom again (after adding all groups and items)
        self.chats_container_layout.addItem(self.bottom_spacer)


class MainWindow(QMainWindow):
    """Main Window Class"""

    def __init__(self, services: Dict[str, Any]):
        super().__init__()
        self.services = services
        # Initialize main controller, inject services to decouple UI and business logic
        self.main_controller = MainController(
            self.services["news_service"],
            self.services["setting_service"],
        )

        self.setWindowTitle("SmartInfo - Minimalist")  # Updated Title
        self.setMinimumSize(1100, 700)  # Adjusted minimum size slightly

        # Flag to indicate if news sources or categories changed in settings
        self.news_sources_or_categories_changed = False

        # Save the current active chat ID
        self.current_chat_id = None

        self._setup_ui()
        logger.info("Main window initialization completed")

    def _setup_ui(self):
        """Set up user interface using injected services"""
        # Central widget and main horizontal layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Left Container (Navigation) ---
        nav_container = QWidget()
        # Optional: Set object name for styling
        nav_container.setObjectName("NavigationContainer")
        nav_container.setFixedWidth(200)
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(0)

        # Instantiate and add the NavigationBar to its container
        self.nav_bar = NavigationBar()
        nav_layout.addWidget(self.nav_bar)
        # Add the navigation container to the main layout
        main_layout.addWidget(nav_container)

        # --- Right Container (Content Stack) ---
        content_container = QWidget()
        # Optional: Set object name for styling
        content_container.setObjectName("ContentContainer")
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(10)

        # Instantiate and add the QStackedWidget to the content container
        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack)
        # Add the content container to the main layout
        main_layout.addWidget(content_container)

        # Set stretch factors: Navigation fixed width, Content expands
        main_layout.setStretch(0, 0)  # Stretch factor for nav_container
        main_layout.setStretch(1, 1)  # Stretch factor for content_container

        # --- Create and Add Pages to Stack ---
        try:
            self.news_tab = NewsTab(self.main_controller.news_controller)
            self.chat_tab = ChatTab(self.main_controller.chat_controller)

        except KeyError as e:
            logger.critical(
                f"Service dictionary missing required key: {e}. Cannot initialize UI.",
                exc_info=True,
            )
            QMessageBox.critical(
                self,
                "Initialization Error",
                f"Required service '{e}' not found. Application cannot start.",
            )
            sys.exit(1)
        except Exception as e:
            logger.critical(
                f"Unexpected error initializing UI tabs: {e}", exc_info=True
            )
            QMessageBox.critical(
                self, "Initialization Error", f"Error creating UI tabs: {e}"
            )
            sys.exit(1)

        # Add pages to the stack widget inside the content_container
        self.stack.addWidget(self.news_tab)
        self.stack.addWidget(self.chat_tab)
        # Set default page
        self.stack.setCurrentIndex(0)

        # --- Connect Signals ---
        # Connect navigation bar signal to handle page changes
        self.nav_bar.page_changed.connect(self._handle_navigation_request)

        # Connect new chat signal
        self.nav_bar.new_chat_clicked.connect(self._handle_new_chat_request)
        self.nav_bar.chat_selected.connect(self._handle_chat_selection)

        # Load chat history
        self._load_chat_history()

        # --- Load Stylesheet ---
        # Ensure this happens after all UI elements are created and added
        self._load_stylesheet()

        # --- Settings Window Instance ---
        self.settings_window_instance: Optional[SettingsWindow] = None

    def _load_chat_history(self):
        """Load chat history and update the sidebar"""
        try:
            # Request chat history
            history_items = self.main_controller.chat_controller.get_history_items()

            # Group chat records by date
            from datetime import datetime, timedelta

            today = datetime.now().date()
            yesterday = today - timedelta(days=1)

            chat_data_list = []

            for item in history_items:
                # Parse date from id (assuming id contains timestamp or has created time field)
                # Here using example logic, should adjust based on your data structure
                if "created_at" in item:
                    chat_date = datetime.fromtimestamp(item["created_at"]).date()
                else:
                    # If no timestamp, assume today
                    chat_date = today

                # Determine group
                if chat_date == today:
                    group = "Today"
                elif chat_date == yesterday:
                    group = "Yesterday"
                else:
                    group = "Others"

                chat_data_list.append(
                    {
                        "id": item["id"],
                        "title": item["title"],
                        "group": group,
                    }
                )

            # Update sidebar
            self.nav_bar.update_chat_groups(chat_data_list)

        except Exception as e:
            logger.error(f"Failed to load chat history: {e}", exc_info=True)

    def _handle_new_chat_request(self):
        """Handle new chat request"""
        logger.info("Received new chat creation request")
        try:
            # Create new chat record in database through controller
            new_chat = self.main_controller.chat_controller.create_new_chat("New Chat")

            # Check if chat creation was successful
            if new_chat is None:
                raise Exception("Database creation of chat failed")

            # Get generated chat ID
            chat_id = new_chat["id"]
            logger.info(f"Successfully created new chat, ID: {chat_id}")

            # Only update UI after successful database operation
            # Add chat to top of Today group
            self.nav_bar._add_chat_item("New Chat", "Today", chat_id, index=0)

            # Switch to chat tab
            self.stack.setCurrentIndex(1)

            # Notify chat interface to prepare new chat
            if hasattr(self, "chat_tab") and self.chat_tab:
                if hasattr(self.chat_tab, "start_new_chat"):
                    self.chat_tab.start_new_chat()
                else:
                    # Alternative: Clear chat display and input box
                    if hasattr(self.chat_tab, "chat_display"):
                        self.chat_tab.chat_display.clear()
                    if hasattr(self.chat_tab, "question_input"):
                        self.chat_tab.question_input.clear()

            # Update current chat ID
            self.current_chat_id = chat_id

        except Exception as e:
            logger.error(f"Failed to create new chat: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Unable to create new chat: {e}")

    def _handle_chat_selection(self, chat_id: str):
        """Handle chat selection"""
        logger.info(f"Selected chat: {chat_id}")

        # Save the currently selected chat ID
        self.current_chat_id = chat_id

        try:
            # Switch to QA tab
            self.stack.setCurrentIndex(1)

            # Notify QA interface to load the selected chat
            if hasattr(self, "chat_tab") and self.chat_tab:
                if hasattr(self.chat_tab, "load_chat"):
                    self.chat_tab.load_chat(chat_id)
                elif hasattr(self.chat_tab, "load_history_item"):
                    self.chat_tab.load_history_item(chat_id)

        except Exception as e:
            logger.error(f"Failed to load chat {chat_id}: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to load chat history: {e}")

    @Slot(int)
    def _handle_navigation_request(self, index: int):
        """Handle page change requests from the navigation bar"""
        logger.debug(f"Navigation requested for index: {index}")

        if index == 0:  # News Tab
            self.stack.setCurrentIndex(index)
            # If settings changed, refresh News Tab filters
            if self.news_sources_or_categories_changed:
                self._refresh_news_tab_filters()
        elif index == 1:  # QA Tab
            self.stack.setCurrentIndex(index)
            # Load QA history
            if hasattr(self, "chat_tab") and self.chat_tab:
                self.chat_tab.load_history()
        elif index == 2:  # Settings Dialog
            logger.info("Settings button clicked. Opening SettingsWindow.")
            try:
                # If SettingsWindow instance doesn't exist or is closed, create a new one
                if (
                    self.settings_window_instance is None
                    or not self.settings_window_instance.isVisible()
                ):
                    logger.debug("Creating new SettingsWindow instance.")
                    # Ensure correct services are passed
                    self.settings_window_instance = SettingsWindow(
                        controller=self.main_controller.settings_controller,
                        parent=self,
                    )
                    # Connect SettingsWindow signal back to MainWindow
                    self.main_controller.settings_controller.external_settings_changed.connect(
                        self._handle_settings_change
                    )
                else:
                    logger.debug(
                        "SettingsWindow instance already exists and is visible."
                    )

                # Show modal dialog and wait for it to close
                self.settings_window_instance.exec()  # Use exec() for modal dialog

            except KeyError as e:
                error_msg = f"Cannot open settings: Missing required service '{e}'."
                logger.error(error_msg)
                QMessageBox.critical(self, "Error", error_msg)
            except Exception as e:
                error_msg = f"Error opening settings window: {e}"
                logger.error(error_msg, exc_info=True)
                QMessageBox.critical(self, "Error", error_msg)
        else:
            logger.warning(f"Unhandled navigation index: {index}")

        # Ensure the correct nav button remains checked after settings dialog closes
        current_stack_index = self.stack.currentIndex()
        for i, btn in enumerate(self.nav_bar.nav_buttons):
            # Check the button corresponding to the current stack index (or settings if index is 2)
            btn.setChecked(i == (index if index == 2 else current_stack_index))

    def _handle_settings_change(self):
        """Slot to handle signal from SettingsTab when sources/categories change."""
        logger.info(
            "Received settings change signal (sources/categories potentially updated)."
        )
        self.news_sources_or_categories_changed = True
        # Check if the NewsTab is currently visible, if so, refresh it immediately
        if self.stack.currentIndex() == 0:  # Index of NewsTab
            self._refresh_news_tab_filters()

    def closeEvent(self, event):
        """Handle window close event"""
        reply = QMessageBox.question(
            self,
            "Confirm exit",
            "Are you sure you want to exit the program?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            logger.info("User confirmed exit. Performing cleanup...")

            # --- Explicitly call cleanup methods for tabs ---
            try:
                if hasattr(self, "news_tab") and hasattr(
                    self.news_tab, "perform_cleanup"
                ):
                    logger.info("Calling NewsTab cleanup...")
                    if not self.news_tab.perform_cleanup():
                        # Optional: Handle case where cleanup fails/timeouts
                        logger.error(
                            "NewsTab cleanup reported issues. Application might not exit cleanly."
                        )

            except Exception as cleanup_err:
                logger.error(f"Error during tab cleanup: {cleanup_err}", exc_info=True)

            logger.info("Cleanup finished. Accepting close event.")
            event.accept()  # Accept the close event AFTER cleanup attempt
        else:
            logger.info("User cancelled exit.")
            event.ignore()

    # Removed _on_tab_changed as it's handled within _handle_navigation_request

    def _refresh_news_tab_filters(self):
        """Refreshes filters on the news tab."""
        if hasattr(self, "news_tab") and self.news_tab:
            logger.info("Refreshing news tab filters due to settings change.")
            self.news_tab.controller.load_filter_options()  # Call controller method to load filters
            self.news_sources_or_categories_changed = False  # Reset flag
        else:
            logger.warning(
                "Attempted to refresh news tab filters, but tab object doesn't exist."
            )

    def _load_stylesheet(self):
        """Load application stylesheet."""
        try:
            logger.debug("Loading application stylesheet...")
            # Base style
            base_style = """
            /* Global Style */
            QWidget {
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px;
                color: #333;
            }
            
            /* Navigation Container Style */
            #NavigationContainer {
                background-color: #f8f9fa;
                border-right: 1px solid #e0e4e7;
            }
            
            /* Navigation Button Style */
            #NavigationBar QPushButton {
                border: none;
                border-radius: 6px;
                padding: 8px 12px;
                text-align: left;
                background-color: transparent;
            }
            
            #NavigationBar QPushButton:hover {
                background-color: #e9ecef;
            }
            
            #NavigationBar QPushButton:checked {
                background-color: #e0e4e7;
                font-weight: bold;
            }
            
            /* Special Style for News Button */
            #NavBtn_News {
                font-weight: bold;
                color: #1976d2;
            }
            
            /* Bottom Settings Button Style */
            #NavBtn_Settings {
                color: #555;
            }
            
            /* Search Box Style */
            #ChatSearchInput {
                border: 1px solid #ddd;
                border-radius: 15px;
                padding: 6px 12px;
                background-color: white;
            }
            
            #ChatSearchInput:focus {
                border-color: #bbdefb;
            }
            
            /* New Chat Button Style */
            #NewChatBtn {
                background-color: #1976d2;
                color: white;
                border-radius: 15px;
                font-weight: bold;
                font-size: 16px;
            }
            
            #NewChatBtn:hover {
                background-color: #1565c0;
            }
            
            /* Chat Group Label Style */
            QLabel[objectName^="ChatGroup_"] {
                font-size: 13px;
                padding: 5px 10px;
                margin-top: 15px;
                margin-bottom: 2px;
                color: #666;
            }
            
            /* Chat Button Style */
            QPushButton[objectName^="ChatBtn_"] {
                text-align: left;
                background-color: transparent;
                border: none;
                border-radius: 5px;
                padding: 4px 10px;
                margin: 0px;
            }
            
            QPushButton[objectName^="ChatBtn_"]:hover {
                background-color: #e9ecef;
            }
            
            QPushButton[objectName^="ChatBtn_"]:checked {
                background-color: #e0f7fa;
                color: #0277bd;
            }
            
            /* Version Label Style */
            #VersionLabel {
                color: #999;
                font-size: 12px;
                padding: 5px;
            }
            
            /* Separator Style */
            #NavSeparator {
                background-color: #ddd;
                height: 1px;
                margin: 5px 10px;
            }
            """

            # Apply stylesheet
            self.setStyleSheet(base_style)
            logger.debug("Stylesheet applied successfully!")

        except Exception as e:
            logger.error(f"Error loading stylesheet: {e}", exc_info=True)
