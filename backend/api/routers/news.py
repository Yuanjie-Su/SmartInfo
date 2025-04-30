# backend/api/routers/news.py
# -*- coding: utf-8 -*-
"""
API router for news functionalities (Version 1).
Handles CRUD for news items, sources, categories, and initiates fetching/analysis tasks.

Endpoints:
- GET /items: List news items with optional filtering
- GET /items/{news_id}: Get a specific news item
- POST /items: Create a new news item
- PUT /items/{news_id}: Update a news item
- PUT /items/{news_id}/analysis: Update analysis for a news item
- DELETE /items/{news_id}: Delete a news item
- DELETE /items/clear: Clear all news items
- POST /items/{news_id}/analyze/stream: Stream analysis for a news item
- GET /sources: List all news sources
- GET /sources/category/{category_id}: List news sources by category
- GET /sources/{source_id}: Get a specific news source
- POST /sources: Create a news source
- PUT /sources/{source_id}: Update a news source
- DELETE /sources/{source_id}: Delete a news source
- GET /categories: List all news categories
- POST /categories: Create a news category
- PUT /categories/{category_id}: Update a news category
- DELETE /categories/{category_id}: Delete a news category
- POST /tasks/fetch/*: Various task endpoints for fetching and analysis
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Body, Query, status
from fastapi.responses import StreamingResponse
from typing import List, Dict, Any, Optional, AsyncGenerator
import uuid
from fastapi import BackgroundTasks

# Import dependencies from the centralized dependencies module
from backend.api.dependencies import get_news_service

# Import schemas from the main models package
from backend.models.schemas.news import (
    NewsItem,
    NewsItemCreate,
    NewsItemUpdate,
    NewsSource,
    NewsSourceCreate,
    NewsSourceUpdate,  # Ensure this exists if needed for PUT
    NewsCategory,
    NewsCategoryCreate,
    NewsCategoryUpdate,
    FetchSourceRequest,
    FetchUrlRequest,
    AnalyzeRequest,
    AnalyzeContentRequest,
    AnalysisResult,  # Usually analysis result is streamed, this might not be used directly
    UpdateAnalysisRequest,
    FetchSourceBatchRequest,
)

# Import the service class type hint
from backend.services.news_service import NewsService

logger = logging.getLogger(__name__)

router = APIRouter()

# --- News Item Endpoints ---


@router.get(
    "/items",
    response_model=List[NewsItem],
    summary="List news items",
    description="Retrieve a paginated list of news items, optionally filtered.",
)
async def get_filtered_news_items(
    category_id: Optional[int] = Query(None, description="Filter by category ID"),
    source_id: Optional[int] = Query(None, description="Filter by source ID"),
    analyzed: Optional[bool] = Query(
        None, description="Filter by analysis status (True/False)"
    ),
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    search_term: Optional[str] = Query(
        None, description="Search term for title/content (case-insensitive)"
    ),
    news_service: NewsService = Depends(get_news_service),
):
    """
    Retrieve news items with various filtering options (category, source,
    analysis status, search term) and pagination.
    """
    try:
        news_items = await news_service.get_news_with_filters(
            category_id=category_id,
            source_id=source_id,
            has_analysis=analyzed,
            page=page,
            page_size=page_size,
            search_term=search_term,
        )
        return news_items
    except Exception as e:
        logger.exception("Failed to retrieve filtered news items", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving news items.",
        )


@router.get(
    "/items/{news_id}",
    response_model=NewsItem,
    summary="Get a specific news item",
)
async def get_news_item_by_id(
    news_id: int, news_service: NewsService = Depends(get_news_service)
):
    """
    Retrieve a single news item by its unique identifier.
    """
    news_item = await news_service.get_news_by_id(news_id)
    if not news_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"News item with ID {news_id} not found.",
        )
    # The service returns a Dict, FastAPI handles conversion to NewsItem response_model
    return news_item


@router.post(
    "/items",
    response_model=NewsItem,
    status_code=status.HTTP_201_CREATED,
    summary="Create a news item",
)
async def create_news_item(
    news_item_data: NewsItemCreate,
    news_service: NewsService = Depends(get_news_service),
):
    """
    Manually create a new news item in the database.
    Requires title and URL. Source and category names/IDs are optional.
    """
    try:
        # Convert Pydantic model to dictionary for the service layer
        news_item_dict = news_item_data.model_dump(exclude_unset=True)

        # The service's create_news expects a dictionary and returns the created item's dict or None
        created_item_dict = await news_service.create_news(news_item_dict)

        if not created_item_dict:
            # Check if failure was due to duplicate URL
            if "url" in news_item_dict and await news_service._news_repo.exists_by_url(
                str(
                    news_item_dict.get("url", "")
                ).strip()  # Ensure URL is string for check
            ):
                url_str = str(news_item_dict.get("url", "")).strip()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"News item with URL '{url_str}' already exists.",
                )
            else:
                # Generic creation failure
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create news item.",
                )
        # Return the created item (FastAPI will validate against NewsItem model)
        return created_item_dict
    except HTTPException:
        raise  # Re-raise HTTP exceptions directly
    except Exception as e:
        logger.exception("Failed to create news item", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the news item.",
        )


@router.put(
    "/items/{news_id}",
    response_model=NewsItem,
    summary="Update a news item",
    description="Update details of an existing news item. Note: URL typically cannot be changed.",
)
async def update_news_item(
    news_id: int,
    news_item_data: NewsItemUpdate,  # Schema allows partial updates
    news_service: NewsService = Depends(get_news_service),
):
    """
    Update an existing news item's details.
    Note: Service-level implementation for update is currently missing.
    """
    try:
        news_item_dict = news_item_data.model_dump(exclude_unset=True)
        if not news_item_dict:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No update data provided.",
            )

        # *** Placeholder: Assumes NewsService.update_news(id, data) exists ***
        # updated_item_data = news_service.update_news(news_id, news_item_dict)
        # if not updated_item_data:
        #     raise HTTPException(
        #         status_code=status.HTTP_404_NOT_FOUND,
        #         detail=f"News item with ID {news_id} not found or update failed."
        #     )
        # return updated_item_data
        # *********************************************************************

        # Raise 501 as the service method is not implemented
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="News item update functionality is not implemented.",
        )
    except HTTPException:
        raise  # Re-raise known HTTP exceptions
    except Exception as e:
        logger.exception(f"Failed to update news item {news_id}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the news item.",
        )


@router.put(
    "/items/{news_id}/analysis",
    summary="Update analysis for a news item",
    response_model=Dict[str, str],  # Simple confirmation message
)
async def update_news_item_analysis(
    news_id: int,
    request: UpdateAnalysisRequest,
    news_service: NewsService = Depends(get_news_service),
):
    """
    Manually update the analysis fields for a news item.
    This allows setting the summary, entities, sentiment, etc. without re-running LLM analysis.
    """
    try:
        # Convert Pydantic model to dictionary for service layer
        update_data = request.model_dump(exclude_unset=True)

        # Call service method
        success = await news_service.update_news_analysis(news_id, update_data)

        if not success:
            # Check if it failed because the news item doesn't exist
            if await news_service.get_news_by_id(news_id) is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"News item with ID {news_id} not found.",
                )
            else:
                # Some other update failure
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Analysis update failed.",
                )

        return {"message": f"Analysis updated for news item {news_id}"}
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.exception(f"Failed to update analysis for news {news_id}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the analysis.",
        )


@router.delete(
    "/items/{news_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a news item",
)
async def delete_news_item(
    news_id: int, news_service: NewsService = Depends(get_news_service)
):
    """
    Permanently delete a news item and its associated analysis data.
    """
    success = await news_service.delete_news(news_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"News item with ID {news_id} not found or deletion failed.",
        )
    # No content to return on successful deletion
    return None


@router.delete(
    "/items/clear",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear all news items (USE WITH CAUTION)",
    description="Permanently deletes all news items from the database.",
)
async def clear_all_news_items(news_service: NewsService = Depends(get_news_service)):
    """
    Dangerous endpoint that removes ALL news items from the database.
    This is mainly for development purposes and should be disabled in production.
    """
    try:
        # This endpoint is intentionally guarded with try-except and logging
        # due to its destructive nature
        logger.warning("Attempting to delete ALL news items from database")
        count = await news_service.clear_all_news()
        logger.warning(f"Successfully deleted {count} news items from database")
        return None
    except Exception as e:
        logger.exception("Failed to clear all news items", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while clearing news items.",
        )


# --- News Source Endpoints ---


@router.get(
    "/sources", response_model=List[NewsSource], summary="List all news sources"
)
async def get_all_news_sources(news_service: NewsService = Depends(get_news_service)):
    """
    Retrieve a list of all configured news sources.
    """
    try:
        sources = await news_service.get_all_sources()
        return sources
    except Exception as e:
        logger.exception("Failed to retrieve news sources", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving news sources.",
        )


@router.get(
    "/sources/category/{category_id}",
    response_model=List[NewsSource],
    summary="List news sources by category",
)
async def get_sources_by_category(
    category_id: int, news_service: NewsService = Depends(get_news_service)
):
    """
    Retrieve all news sources belonging to a specific category.
    Returns an empty list if the category has no associated sources.
    """
    try:
        # Verify category exists first
        category = await news_service.get_category_by_id(category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category with ID {category_id} not found.",
            )

        # Get sources for the category
        sources = await news_service.get_sources_by_category_id(category_id)
        return sources
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            f"Failed to retrieve sources for category {category_id}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving category sources.",
        )


@router.get(
    "/sources/{source_id}",
    response_model=NewsSource,
    summary="Get a specific news source",
)
async def get_news_source_by_id(
    source_id: int, news_service: NewsService = Depends(get_news_service)
):
    """
    Retrieve a single news source by its unique identifier.
    """
    source = await news_service.get_source_by_id(source_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"News source with ID {source_id} not found.",
        )
    return source


@router.post(
    "/sources",
    response_model=NewsSource,
    status_code=status.HTTP_201_CREATED,
    summary="Create a news source",
)
async def create_news_source(
    source_data: NewsSourceCreate, news_service: NewsService = Depends(get_news_service)
):
    """
    Create a new news source configuration.

    Required fields:
    - name: Unique name for the source
    - url: Base URL of the source
    - category_id: ID of the category the source belongs to
    """
    try:
        # Convert to dictionary for service layer
        source_data_dict = source_data.model_dump(exclude_unset=True)

        # Basic validation
        url = str(source_data_dict.get("url", "")).strip()
        name = source_data_dict.get("name", "").strip()
        category_id = source_data_dict.get("category_id")

        if not all([name, url, category_id]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Name, URL and category ID are required.",
            )

        # Attempt to create the source
        created_source = await news_service.create_source(
            {
                "name": name,
                "url": url,
                "category_id": category_id,
            }
        )
        if not created_source:
            # Check if it's because the name already exists
            if await news_service._source_repo.exists_by_name(name):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"News source with name '{name}' already exists.",
                )
            # Or because the URL already exists
            elif await news_service._source_repo.exists_by_url(url):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"News source with URL '{url}' already exists.",
                )
            else:
                # Generic creation error
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create news source.",
                )

        return created_source
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.exception("Failed to create news source", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the news source.",
        )


@router.put(
    "/sources/{source_id}",
    response_model=NewsSource,
    summary="Update a news source",
)
async def update_news_source(
    source_id: int,
    source_data: NewsSourceUpdate,  # Using partial update schema
    news_service: NewsService = Depends(get_news_service),
):
    """
    Update an existing news source configuration.
    Allows partial updates - only the fields included in the request will be changed.

    Note: When updating RSS feed URL or selectors, ensure the new values will still
    work with the source's content structure.
    """
    try:
        # First check if the source exists
        existing_source = await news_service.get_source_by_id(source_id)
        if not existing_source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"News source with ID {source_id} not found.",
            )

        # Get the update data as dictionary
        source_data_dict = source_data.model_dump(exclude_unset=True)
        if not source_data_dict:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No update data provided.",
            )

        # Basic validation on selected fields if they're included in the update
        if "name" in source_data_dict:
            name = source_data_dict.get("name", "").strip()
            if not name:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Name cannot be empty.",
                )
            # Check for duplicate name, but allow the same name as current
            if name != existing_source[
                "name"
            ] and await news_service._source_repo.exists_by_name(name):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"News source with name '{name}' already exists.",
                )

        if "url" in source_data_dict:
            url = str(source_data_dict.get("url", "")).strip()
            if not url:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="URL cannot be empty.",
                )
            # Check for duplicate URL, but allow the same URL as current
            if url != existing_source[
                "url"
            ] and await news_service._source_repo.exists_by_url(url):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"News source with URL '{url}' already exists.",
                )

        # Ensure we're not removing both RSS and selectors
        has_rss = (
            source_data_dict.get(
                "rss_feed_url", existing_source.get("rss_feed_url", "")
            )
            != ""
        )
        has_selectors = (
            source_data_dict.get(
                "selector_headline", existing_source.get("selector_headline", "")
            )
            != ""
            and source_data_dict.get(
                "selector_content", existing_source.get("selector_content", "")
            )
            != ""
        )

        if "rss_feed_url" in source_data_dict and not source_data_dict["rss_feed_url"]:
            # If removing RSS feed, ensure we have selectors
            if not has_selectors:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot remove RSS feed without having headline and content selectors.",
                )

        if (
            "selector_headline" in source_data_dict
            and not source_data_dict["selector_headline"]
        ) or (
            "selector_content" in source_data_dict
            and not source_data_dict["selector_content"]
        ):
            # If removing selectors, ensure we have RSS
            if not has_rss:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot remove HTML selectors without having an RSS feed URL.",
                )

        # Update the source
        updated_source = await news_service.update_source(source_id, source_data_dict)
        if not updated_source:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update news source.",
            )

        return updated_source
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.exception(f"Failed to update news source {source_id}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the news source.",
        )


@router.delete(
    "/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a news source",
)
async def delete_news_source(
    source_id: int, news_service: NewsService = Depends(get_news_service)
):
    """
    Delete a news source configuration.
    This does not delete any news items that were already fetched from this source.
    """
    success = await news_service.delete_source(source_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"News source with ID {source_id} not found or deletion failed.",
        )
    # No content to return on successful deletion
    return None


# --- News Category Endpoints ---


@router.get(
    "/categories",
    response_model=List[NewsCategory],
    summary="List all news categories",
)
async def get_all_news_categories(
    news_service: NewsService = Depends(get_news_service),
):
    """
    Retrieve a list of all news categories.
    Categories are used to organize news sources.
    """
    try:
        categories = await news_service.get_all_categories()
        logger.info(f"Retrieved {len(categories)} news categories: {categories}")
        return categories
    except Exception as e:
        logger.exception("Failed to retrieve news categories", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving news categories.",
        )


@router.post(
    "/categories",
    response_model=NewsCategory,
    status_code=status.HTTP_201_CREATED,
    summary="Create a news category",
)
async def create_news_category(
    category_data: NewsCategoryCreate,
    news_service: NewsService = Depends(get_news_service),
):
    """
    Create a new news category.
    Categories are used to organize news sources and provide filtering options.
    """
    try:
        # Convert to dictionary for service layer
        category_data_dict = category_data.model_dump()

        # Validate name
        name = category_data_dict.get("name", "").strip()
        if not name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category name is required.",
            )

        # Create the category
        created_category = await news_service.create_category(category_data_dict)
        if not created_category:
            # Check if it's because the name already exists
            if await news_service._category_repo.exists_by_name(name):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"News category with name '{name}' already exists.",
                )
            else:
                # Generic creation error
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create news category.",
                )

        return created_category
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.exception("Failed to create news category", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the news category.",
        )


@router.put(
    "/categories/{category_id}",
    response_model=NewsCategory,
    summary="Update a news category",
)
async def update_news_category(
    category_id: int,
    category_data: NewsCategoryUpdate,
    news_service: NewsService = Depends(get_news_service),
):
    """
    Update an existing news category's details.
    """
    try:
        # First check if category exists
        existing_category = await news_service.get_category_by_id(category_id)
        if not existing_category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"News category with ID {category_id} not found.",
            )

        # Get update data as dictionary
        category_data_dict = category_data.model_dump(exclude_unset=True)
        if not category_data_dict:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No update data provided.",
            )

        # Validate name if it's being updated
        if "name" in category_data_dict:
            name = category_data_dict["name"].strip()
            if not name:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Category name cannot be empty.",
                )

            # Check for duplicate name, but allow the same name as current
            if name != existing_category[
                "name"
            ] and await news_service._category_repo.exists_by_name(name):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"News category with name '{name}' already exists.",
                )

        # Update the category
        updated_category = await news_service.update_category(
            category_id, category_data_dict
        )
        if not updated_category:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update news category.",
            )

        return updated_category
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.exception(f"Failed to update news category {category_id}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the news category.",
        )


@router.delete(
    "/categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a news category",
)
async def delete_news_category(
    category_id: int, news_service: NewsService = Depends(get_news_service)
):
    """
    Delete a news category.
    This will remove the category from any associated news sources,
    but not delete the sources themselves.
    """
    success = await news_service.delete_category(category_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"News category with ID {category_id} not found or deletion failed.",
        )
    # No content to return on successful deletion
    return None


# --- News Fetching and Processing Endpoints ---


@router.post(
    "/tasks/fetch/url",
    status_code=status.HTTP_200_OK,  # 200 OK as it processes directly (for now)
    summary="Fetch and process a single URL immediately",
    response_model=Dict[str, Any],
)
async def trigger_fetch_single_url(
    request: FetchUrlRequest, news_service: NewsService = Depends(get_news_service)
):
    """
    Fetch and process a single URL immediately.
    Unlike the other fetch endpoints, this one runs synchronously and returns the result.

    You can optionally specify a source_id to associate the news with, and set
    should_analyze=True to immediately run analysis on the fetched content.
    """
    try:
        url = str(request.url).strip()
        source_id = request.source_id  # Can be None
        should_analyze = request.should_analyze or False

        # Basic URL validation
        if not url or not url.startswith(("http://", "https://")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid URL. Must be a fully qualified HTTP or HTTPS URL.",
            )

        # Check if the URL already exists in the database
        if await news_service._news_repo.exists_by_url(url):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A news item with this URL already exists in the database.",
            )

        # If source_id provided, validate it exists
        if source_id is not None:
            source = await news_service.get_source_by_id(source_id)
            if not source:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"News source with ID {source_id} not found.",
                )

        # Process the URL
        result = await news_service.fetch_single_url(url, source_id, should_analyze)
        if not result or "news_id" not in result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process the URL.",
            )

        return result
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.exception(
            f"Failed to fetch single URL: {str(request.url).strip()}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching the URL: {str(e)}",
        )


@router.post(
    "/tasks/fetch/batch",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start fetching news from multiple sources in parallel",
    response_model=Dict[str, str],
)
async def trigger_fetch_batch_sources(
    request: FetchSourceBatchRequest,
    background_tasks: BackgroundTasks,
    news_service: NewsService = Depends(get_news_service),
):
    """
    Start background tasks to fetch news from multiple sources in parallel.
    Each source is processed as a separate task, and progress can be monitored
    via WebSocket connection.

    Returns a task_group_id that can be used to connect to the WebSocket endpoint
    to monitor progress.
    """
    try:
        if not request.source_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No source IDs provided.",
            )

        # Generate a unique task group ID
        task_group_id = str(uuid.uuid4())

        # Schedule background tasks with this task group ID
        await news_service.fetch_sources_in_background(
            request.source_ids, task_group_id, background_tasks
        )

        logger.info(
            f"Scheduled background tasks for {len(request.source_ids)} sources with task_group_id: {task_group_id}"
        )

        # Return the task group ID for WebSocket monitoring
        return {
            "task_group_id": task_group_id,
            "message": f"Fetch tasks scheduled for {len(request.source_ids)} sources.",
        }

    except Exception as e:
        logger.exception("Error scheduling batch source fetch", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to schedule batch fetch: {str(e)}",
        )


# --- News Analysis Endpoints ---


@router.post(
    "/tasks/analyze/all",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start analysis for all news items",
    response_model=Dict[str, str],
)
async def trigger_analyze_all_news(
    request: AnalyzeRequest = Body(..., description="Analysis request parameters"),
    news_service: NewsService = Depends(get_news_service),
):
    """
    Start a background task to analyze all unanalyzed news items.
    This process uses the LLM to extract entities, summarize, etc.

    This is a non-blocking call that immediately returns, while analysis continues in the background.
    """
    try:
        # Start the analysis process for all news in the background
        force_reanalysis = request.force_reanalysis or False
        await news_service.analyze_all_news_background(force_reanalysis)
        return {"message": "News analysis started successfully."}
    except Exception as e:
        logger.exception("Failed to start news analysis", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start news analysis process.",
        )


@router.post(
    "/tasks/analyze/items",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start analysis for specific news items",
    response_model=Dict[str, str],
)
async def trigger_analyze_news_by_ids(
    request: AnalyzeRequest = Body(
        ..., description="Analysis request with specific news IDs"
    ),
    news_service: NewsService = Depends(get_news_service),
):
    """
    Start a background task to analyze specific news items by their IDs.
    This process uses the LLM to extract entities, summarize, etc.

    This is a non-blocking call that immediately returns, while analysis continues in the background.
    """
    try:
        news_ids = request.news_ids
        force_reanalysis = request.force_reanalysis or False

        if not news_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No news items specified for analysis.",
            )

        # Validate that all news IDs exist
        for news_id in news_ids:
            if await news_service.get_news_by_id(news_id) is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"News item with ID {news_id} not found.",
                )

        # Start analyzing the specified news items
        await news_service.analyze_news_by_ids_background(news_ids, force_reanalysis)
        num_items = len(news_ids)
        return {
            "message": f"Analysis started for {num_items} news item{'s' if num_items != 1 else ''}."
        }
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.exception(
            "Failed to start news analysis for specific items", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start news analysis process.",
        )


@router.post(
    "/analyze/content",
    summary="Analyze provided content with instructions",
    response_class=StreamingResponse,  # Stream the analysis back
    description="Analyze arbitrary text content using the LLM based on provided instructions. The result is streamed.",
)
async def analyze_arbitrary_content(
    request: AnalyzeContentRequest,
    news_service: NewsService = Depends(get_news_service),
):
    """
    Analyze arbitrary text content using the LLM.
    This endpoint allows streaming the results back as they're generated.

    The analysis is controlled by the instructions provided in the request.
    """
    try:
        # Check we have content and instructions
        if not request.content or not request.content.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Content to analyze cannot be empty.",
            )

        if not request.instructions or not request.instructions.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Analysis instructions cannot be empty.",
            )

        # Define the generator for streaming
        async def stream_generator():
            async for chunk in await news_service.analyze_content_streaming(
                content=request.content, instructions=request.instructions
            ):
                yield f"{chunk}"

        # Return a streaming response
        return StreamingResponse(
            stream_generator(),
            media_type="text/plain",
        )
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.exception("Failed to analyze content", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during content analysis: {str(e)}",
        )


@router.post(
    "/items/{news_id}/analyze/stream",
    summary="Stream analysis for a specific news item",
    description="Streams analysis for a news item. If analysis already exists, returns it directly. If not, generates a new analysis and streams it in real-time.",
    response_class=StreamingResponse,
)
async def stream_news_item_analysis(
    news_id: int,
    force: bool = Query(False, description="Force re-analysis even if analysis exists"),
    news_service: NewsService = Depends(get_news_service),
):
    """
    Streams analysis for a specific news item.
    If analysis already exists, returns it directly.
    If not, triggers LLM analysis and streams the results as they are generated.

    After streaming completes, the analysis is saved to the database.
    """
    # Check if the news item exists
    news_item = await news_service.get_news_by_id(news_id)
    if not news_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"News item with ID {news_id} not found.",
        )

    # Setup the streaming response with the analysis generator
    return StreamingResponse(
        news_service.stream_analysis_for_news_item(news_id, force),
        media_type="text/plain",
    )
