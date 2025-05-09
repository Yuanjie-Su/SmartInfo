#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
NewsService Module
- Coordinates retrieval, processing, analysis, and storage of news content for specific users.
- Utilizes an LLM for link extraction and in-depth content summarization.
"""

from datetime import date
import logging
from typing import List, Dict, Optional, Any, AsyncGenerator

# Repository interfaces for database operations
from db.repositories import (
    NewsRepository,
    NewsSourceRepository,
    NewsCategoryRepository,
    ApiKeyRepository,  # Import ApiKeyRepository
)

# Client to interact with the LLM API
from core.llm.client import AsyncLLMClient  # Import AsyncLLMClient

from utils.prompt import SYSTEM_PROMPT_ANALYZE_CONTENT
from models import (
    NewsSourceCreate,
    NewsCategoryCreate,
    User,  # Import Pydantic models
    ApiKey,  # Import ApiKey model
)

# Configure module-level logger
logger = logging.getLogger(__name__)


class NewsService:
    """
    Service class responsible for user-specific:
    - Fetching and cleaning HTML content.
    - Converting to Markdown and chunking large texts.
    - Extracting article links via LLM.
    - Crawling extracted links for sub-content.
    - Performing LLM-driven content analysis.
    - Parsing analysis results and saving to database.
    - Providing CRUD operations for news items, sources, and categories.
    """

    def __init__(
        self,
        news_repo: NewsRepository,
        source_repo: NewsSourceRepository,
        category_repo: NewsCategoryRepository,
        api_key_repo: ApiKeyRepository,  # Add ApiKeyRepository dependency
    ):
        self._news_repo = news_repo
        self._source_repo = source_repo
        self._category_repo = category_repo
        self._api_key_repo = api_key_repo  # Store ApiKeyRepository

    # -------------------------------------------------------------------------
    # Public CRUD Methods (User-Aware)
    # -------------------------------------------------------------------------
    # --- News Item Methods ---
    async def get_news_by_id(
        self, news_id: int, user_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get a news item by ID for a specific user."""
        record = await self._news_repo.get_by_id(news_id, user_id)
        return dict(record) if record else None

    async def get_all_news(
        self, user_id: int, limit: int = 100, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get all news items for a specific user with pagination."""
        records = await self._news_repo.get_all(user_id, limit, offset)
        return [dict(record) for record in records]

    async def get_news_with_filters(
        self,
        user_id: int,  # Add user_id
        category_id: Optional[int] = None,
        source_id: Optional[int] = None,
        has_analysis: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
        search_term: Optional[str] = None,
        fetch_date: Optional[date] = None,  # New parameter
        sort_by: Optional[str] = None,  # New parameter
    ) -> List[Dict[str, Any]]:
        """Get news items for a specific user with filters."""
        # Use get_news_with_filters_as_dict which already handles user_id and returns dicts
        return await self._news_repo.get_news_with_filters_as_dict(
            user_id=user_id,
            category_id=category_id,
            source_id=source_id,
            analyzed=has_analysis,
            page=page,
            page_size=page_size,
            search_term=search_term,
            fetch_date=fetch_date,  # Pass new parameter
            sort_by=sort_by,  # Pass new parameter
        )

    async def update_news(
        self, news_id: int, user_id: int, news_item: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a news item for a specific user. Not implemented yet."""
        # TODO: Implement news update logic, ensuring user_id check
        logger.warning(
            f"update_news not implemented yet (news_id: {news_id}, user_id: {user_id})"
        )
        # Example check:
        # existing = await self._news_repo.get_by_id(news_id, user_id)
        # if not existing: return None
        # ... perform update using self._news_repo.update(...)
        return None

    async def delete_news(self, news_id: int, user_id: int) -> bool:
        """Delete a news item for a specific user."""
        return await self._news_repo.delete(news_id, user_id)

    async def clear_all_news_for_user(self, user_id: int) -> bool:
        """Clear all news items for a specific user."""
        return await self._news_repo.clear_all_for_user(user_id)

    # --- Category Methods ---
    async def get_all_categories(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all categories for a specific user."""
        records = await self._category_repo.get_all(user_id)
        return [dict(record) for record in records]

    async def get_all_categories_with_counts(
        self, user_id: int
    ) -> List[Dict[str, Any]]:
        """Get all categories for a user with news source counts (also user-specific)."""
        records = await self._category_repo.get_with_source_count(user_id)
        return [dict(record) for record in records]

    async def get_category_by_id(
        self, category_id: int, user_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get a category by ID for a specific user."""
        record = await self._category_repo.get_by_id(category_id, user_id)
        return dict(record) if record else None

    async def add_category(self, name: str, user_id: int) -> Optional[int]:
        """Add a new category for a specific user."""
        return await self._category_repo.add(name, user_id)

    async def create_category(
        self, category_data: NewsCategoryCreate, user_id: int  # Use Pydantic model
    ) -> Optional[Dict[str, Any]]:
        """Create a new category for a user using Pydantic model data."""
        if category_data.user_id != user_id:
            raise ValueError(
                "User ID in category data does not match authenticated user."
            )
        name = category_data.name.strip()
        if not name:
            return None

        category_id = await self._category_repo.add(name, user_id)
        if not category_id:
            return None

        return {"id": category_id, "name": name, "user_id": user_id}

    async def update_category(
        self, category_id: int, user_id: int, new_name: str
    ) -> bool:
        """Update a category name for a specific user."""
        return await self._category_repo.update(category_id, user_id, new_name)

    async def update_category_from_dict(
        self, category_id: int, user_id: int, category_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a category for a user using data from a dictionary."""
        new_name = category_data.get("name", "").strip()
        if not new_name:
            return None

        success = await self._category_repo.update(category_id, user_id, new_name)
        if not success:
            return None

        category = await self._category_repo.get_by_id(category_id, user_id)
        return dict(category) if category else None

    async def delete_category(self, category_id: int, user_id: int) -> bool:
        """Delete a category for a specific user."""
        return await self._category_repo.delete(category_id, user_id)

    # --- Source Methods ---
    async def get_all_sources(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all news sources for a specific user with category information."""
        records = await self._source_repo.get_all(user_id)
        return [dict(record) for record in records]

    async def get_sources_by_category_id(
        self, category_id: int, user_id: int
    ) -> List[Dict[str, Any]]:
        """Get all news sources for a specific category belonging to a user."""
        records = await self._source_repo.get_by_category(category_id, user_id)
        return [dict(record) for record in records]

    async def get_source_by_id(
        self, source_id: int, user_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get a news source by ID for a specific user with category information."""
        record = await self._source_repo.get_by_id(source_id, user_id)
        return dict(record) if record else None

    async def add_source(
        self, name: str, url: str, category_name: str, user_id: int
    ) -> Optional[int]:
        """Add a news source for a user. Creates the category if it doesn't exist for the user."""
        category = await self._category_repo.get_by_name(category_name, user_id)
        if category:
            category_id = category["id"]  # Access by key name
        else:
            category_id = await self._category_repo.add(category_name, user_id)
            if not category_id:
                logger.error(
                    f"Failed to create category '{category_name}' for user {user_id}"
                )
                return None

        return await self._source_repo.add(name, url, category_id, user_id)

    async def update_source(
        self, source_id: int, user_id: int, name: str, url: str, category_name: str
    ) -> bool:
        """Update a news source for a user. Creates the category if it doesn't exist for the user."""
        category = await self._category_repo.get_by_name(category_name, user_id)
        if category:
            category_id = category["id"]
        else:
            category_id = await self._category_repo.add(category_name, user_id)
            if not category_id:
                logger.error(
                    f"Failed to create category '{category_name}' for user {user_id}"
                )
                return False

        return await self._source_repo.update(
            source_id, user_id, name, url, category_id
        )

    async def delete_source(self, source_id: int, user_id: int) -> bool:
        """Delete a news source for a specific user."""
        return await self._source_repo.delete(source_id, user_id)

    async def update_news_analysis(
        self, news_id: int, user_id: int, analysis_text: str
    ) -> bool:
        """Update the analysis field of a news item for a specific user."""
        return await self._news_repo.update_analysis(news_id, user_id, analysis_text)

    async def create_source(
        self, source_data: NewsSourceCreate, user_id: int  # Use Pydantic model
    ) -> Optional[Dict[str, Any]]:
        """Create a news source for a user from Pydantic model data."""
        if source_data.user_id != user_id:
            raise ValueError(
                "User ID in source data does not match authenticated user."
            )

        name = source_data.name.strip()
        url = str(source_data.url)  # Convert AnyHttpUrl to string if needed by repo
        category_id = source_data.category_id

        if not name or not url or not category_id:
            logger.warning(
                f"Missing required fields for source creation for user {user_id}"
            )
            return None

        # Check if category exists for the user
        category = await self._category_repo.get_by_id(category_id, user_id)
        if not category:
            logger.warning(f"Category ID {category_id} not found for user {user_id}")
            return None

        # Check if source with name or URL already exists for the user
        # Assuming get_by_name exists in NewsSourceRepository
        existing_by_name = await self._source_repo.get_by_name(name, user_id)
        if existing_by_name:
            logger.warning(
                f"Source with name '{name}' already exists for user {user_id}"
            )
            return dict(existing_by_name)

        existing_by_url = await self._source_repo.get_by_url(url, user_id)
        if existing_by_url:
            logger.warning(f"Source with URL '{url}' already exists for user {user_id}")
            return dict(existing_by_url)

        source_id = await self._source_repo.add(
            name=name, url=url, category_id=category_id, user_id=user_id
        )
        if not source_id:
            logger.error(f"Failed to add source to database for user {user_id}")
            return None

        # Fetch the full source details including category name
        new_source = await self.get_source_by_id(source_id, user_id)
        return new_source  # Already a dict

    async def stream_analysis_for_news_item(
        self, news_id: int, user_id: int, force: bool = False  # Add user_id
    ) -> AsyncGenerator[str, None]:
        """
        Analyzes a specific news item belonging to a user and streams the results.
        """
        llm_client = await self._get_user_llm_client(user_id)
        if llm_client is None:
            yield "Error: No valid LLM API key found for your account."
            return

        logger.info(f"Stream analyzing news item ID: {news_id} for user {user_id}")

        try:
            # Check if analysis already exists for this user's item
            if not force:
                # Need get_analysis_by_id in repo to accept user_id
                analysis = await self._news_repo.get_analysis_by_id(news_id, user_id)
                if analysis:
                    logger.info(
                        f"Using existing analysis for news item {news_id} (User: {user_id})"
                    )
                    yield analysis
                    return

            # Get the content for analysis, ensuring ownership
            news_content = await self._news_repo.get_content_by_id(news_id, user_id)
            if not news_content:
                logger.error(
                    f"No content found for news item {news_id} or not owned by user {user_id}"
                )
                yield "Error: No content available for analysis or item not found."
                return

            user_prompt = f"""
                Please analyze the following news content:\n\"\"\"\n{news_content}\n\"\"\"
                **Write in the same language as the original content** (e.g., if the original content is in Chinese, the analysis should also be in Chinese).
                """

            full_analysis = ""
            llm_reponse_stream = llm_client.stream_completion_content(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_ANALYZE_CONTENT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=4096,
                temperature=0.7,
            )

            async for chunk in llm_reponse_stream:
                full_analysis += chunk
                print(chunk, end="", flush=True)  # Debugging output
                yield chunk

            await llm_client.close()

            if full_analysis:
                try:
                    # Pass user_id to update_analysis
                    await self._news_repo.update_analysis(
                        news_id, user_id, full_analysis
                    )
                    logger.info(
                        f"Saved analysis for news item {news_id} (User: {user_id})"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to save analysis for news item {news_id} (User: {user_id}): {e}"
                    )

        except Exception as e:
            logger.error(
                f"Error in stream_analysis_for_news_item (User: {user_id}): {e}"
            )
            yield f"Error during analysis: {str(e)}"

    async def _get_user_llm_client(self, user_id: int) -> Optional[AsyncLLMClient]:
        """
        Fetches user's API key configuration and instantiates an AsyncLLMClient.
        Returns None if no valid key is found.
        """
        api_keys_data = await self._api_key_repo.get_all(user_id)

        if not api_keys_data:
            logger.warning(f"No API keys found for user {user_id}.")
            return None

        # Use the first valid API key found
        for key_data in api_keys_data:
            try:
                api_key = ApiKey.model_validate(dict(key_data))
                logger.info(f"Using API key ID {api_key.id} for user {user_id}.")
                return AsyncLLMClient(
                    base_url=api_key.base_url,
                    api_key=api_key.api_key,
                    model=api_key.model,
                    context=api_key.context,
                    max_output_tokens=api_key.max_output_tokens,
                )
            except Exception as e:
                logger.error(
                    f"Failed to validate or instantiate LLM client for API key data: {key_data}. Error: {e}",
                    exc_info=True,
                )
                continue  # Try the next key

        logger.warning(f"No valid API key configuration found for user {user_id}.")
        return None
