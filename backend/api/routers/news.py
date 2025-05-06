# backend/api/routers/news.py
# -*- coding: utf-8 -*-
"""
API router for user-specific news functionalities (Version 1).
Handles CRUD for news items, sources, categories, and initiates fetching/analysis tasks for the authenticated user.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Body, Query, status
from fastapi.responses import StreamingResponse
from typing import (
    List,
    Dict,
    Any,
    Optional,
    AsyncGenerator,
    Annotated,
)  # Import Annotated
import uuid

# Import dependencies from the centralized dependencies module
from api.dependencies import (
    get_news_service,
    get_current_active_user,
)  # Import user dependency

# Import schemas from the main models package
from models import (  # Import models directly
    News,
    NewsCreate,
    NewsUpdate,
    NewsSource,
    NewsSourceCreate,
    NewsSourceUpdate,
    NewsCategory,
    NewsCategoryCreate,
    NewsCategoryUpdate,
    FetchSourceRequest,
    FetchUrlRequest,
    AnalyzeRequest,
    AnalyzeContentRequest,
    AnalysisResult,
    UpdateAnalysisRequest,
    FetchSourceBatchRequest,
    User,  # Import User schema
)

# Import the service class type hint
from services.news_service import NewsService

logger = logging.getLogger(__name__)

router = APIRouter()

# --- News Item Endpoints (User-Aware) ---


@router.get(
    "/items",
    response_model=List[News],
    summary="List user's news items",
    description="Retrieve a paginated list of news items belonging to the current user, optionally filtered.",
)
async def get_filtered_news_items(
    current_user: Annotated[User, Depends(get_current_active_user)],
    news_service: Annotated[
        NewsService, Depends(get_news_service)
    ],  # Moved Depends before Query
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
):
    """
    Retrieve news items for the current user with various filtering options.
    """
    try:
        news_items = await news_service.get_news_with_filters(
            user_id=current_user.id,  # Pass user_id
            category_id=category_id,
            source_id=source_id,
            has_analysis=analyzed,
            page=page,
            page_size=page_size,
            search_term=search_term,
        )
        # Service method returns dicts, FastAPI handles response model validation
        return news_items
    except Exception as e:
        logger.exception(
            "Failed to retrieve filtered news items for user", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving news items.",
        )


@router.get(
    "/items/{news_id}",
    response_model=News,
    summary="Get a specific news item",
)
async def get_news_item_by_id(
    news_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    news_service: Annotated[NewsService, Depends(get_news_service)],
):
    """
    Retrieve a single news item by its ID, ensuring it belongs to the current user.
    """
    news_item = await news_service.get_news_by_id(
        news_id=news_id, user_id=current_user.id
    )
    if not news_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"News item with ID {news_id} not found or not owned by user.",
        )
    return news_item


@router.post(
    "/items",
    response_model=News,
    status_code=status.HTTP_201_CREATED,
    summary="Create a news item",
    description="Manually create a new news item for the current user.",
)
async def create_news_item(
    news_item_data: NewsCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    news_service: Annotated[NewsService, Depends(get_news_service)],
):
    """
    Manually create a new news item for the current user.
    Requires title and URL. Source/category IDs must belong to the user.
    """
    # Ensure the item data is associated with the current user
    news_item_data_with_user = news_item_data.model_copy(
        update={"user_id": current_user.id}
    )

    try:
        # Assuming service method `create_news` exists and handles user_id
        # If not, need to implement it or call repo directly after validation
        # created_item_dict = await news_service.create_news(news_item_data_with_user)

        # Placeholder: Directly call repo add (assuming service method not implemented yet)
        # Need validation for category_id and source_id ownership if calling repo directly
        if news_item_data_with_user.category_id:
            cat = await news_service.get_category_by_id(
                news_item_data_with_user.category_id, current_user.id
            )
            if not cat:
                raise HTTPException(
                    status_code=400,
                    detail=f"Category ID {news_item_data_with_user.category_id} not found or not owned by user.",
                )
        if news_item_data_with_user.source_id:
            src = await news_service.get_source_by_id(
                news_item_data_with_user.source_id, current_user.id
            )
            if not src:
                raise HTTPException(
                    status_code=400,
                    detail=f"Source ID {news_item_data_with_user.source_id} not found or not owned by user.",
                )

        item_dict = news_item_data_with_user.model_dump(exclude_unset=True)
        created_id = await news_service._news_repo.add(
            item=item_dict, user_id=current_user.id
        )

        if not created_id:
            # Check for duplicate URL for this user
            url_str = str(item_dict.get("url", "")).strip()
            if await news_service._news_repo.exists_by_url(
                url=url_str, user_id=current_user.id
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"News item with URL '{url_str}' already exists for this user.",
                )
            else:
                raise HTTPException(
                    status_code=500, detail="Failed to create news item."
                )

        created_item_dict = await news_service.get_news_by_id(
            created_id, current_user.id
        )
        if not created_item_dict:  # Should not happen
            raise HTTPException(
                status_code=500, detail="Failed to retrieve created news item."
            )

        return created_item_dict
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to create news item", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the news item.",
        )


@router.put(
    "/items/{news_id}",
    response_model=News,
    summary="Update a news item",
    description="Update details of an existing news item belonging to the current user.",
)
async def update_news_item(
    news_id: int,
    news_item_data: NewsUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    news_service: Annotated[NewsService, Depends(get_news_service)],
):
    """
    Update an existing news item's details for the current user.
    Service-level implementation for update is currently missing.
    """
    try:
        news_item_dict = news_item_data.model_dump(exclude_unset=True)
        if not news_item_dict:
            raise HTTPException(status_code=400, detail="No update data provided.")

        # *** Placeholder: Assumes NewsService.update_news(id, user_id, data) exists ***
        # updated_item_data = await news_service.update_news(news_id, current_user.id, news_item_dict)
        # if not updated_item_data:
        #     raise HTTPException(status_code=404, detail=f"News item {news_id} not found or not owned by user.")
        # return updated_item_data
        # *********************************************************************

        raise HTTPException(status_code=501, detail="News item update not implemented.")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update news item {news_id}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error updating news item.")


@router.put(
    "/items/{news_id}/analysis",
    summary="Update analysis for a news item",
    response_model=Dict[str, str],
)
async def update_news_item_analysis(
    news_id: int,
    request: UpdateAnalysisRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    news_service: Annotated[NewsService, Depends(get_news_service)],
):
    """
    Manually update the analysis field for a news item belonging to the current user.
    """
    try:
        # Service method checks ownership
        success = await news_service.update_news_analysis(
            news_id=news_id, user_id=current_user.id, analysis_text=request.analysis
        )
        if not success:
            # Check if item exists for user to give 404 vs 500
            if await news_service.get_news_by_id(news_id, current_user.id) is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"News item {news_id} not found or not owned by user.",
                )
            else:
                raise HTTPException(status_code=500, detail="Analysis update failed.")
        return {"message": f"Analysis updated for news item {news_id}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update analysis for news {news_id}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error updating analysis.")


@router.delete(
    "/items/{news_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a news item",
)
async def delete_news_item(
    news_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    news_service: Annotated[NewsService, Depends(get_news_service)],
):
    """
    Permanently delete a news item belonging to the current user.
    """
    success = await news_service.delete_news(news_id=news_id, user_id=current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"News item {news_id} not found or not owned by user.",
        )
    return None


@router.delete(
    "/items/clear",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear all user's news items (USE WITH CAUTION)",
    description="Permanently deletes all news items belonging to the current user.",
)
async def clear_all_my_news_items(
    current_user: Annotated[User, Depends(get_current_active_user)],
    news_service: Annotated[NewsService, Depends(get_news_service)],
):
    """
    Removes ALL news items belonging to the current user.
    """
    try:
        logger.warning(
            f"Attempting to delete ALL news items for user {current_user.id}"
        )
        success = await news_service.clear_all_news_for_user(user_id=current_user.id)
        # Repo method returns bool, but doesn't indicate count easily. Log success/failure.
        if success:
            logger.warning(
                f"Successfully cleared news items for user {current_user.id}"
            )
        else:
            # This might happen if there were no items or a DB error occurred
            logger.error(f"Failed to clear news items for user {current_user.id}")
            # Raise error even if it might just mean no items existed? Or just return success?
            # Let's assume success means the operation completed without DB error.
            pass
        return None
    except Exception as e:
        logger.exception(
            f"Failed to clear news items for user {current_user.id}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Error clearing news items.")


# --- News Source Endpoints (User-Aware) ---


@router.get(
    "/sources", response_model=List[NewsSource], summary="List user's news sources"
)
async def get_all_news_sources(
    current_user: Annotated[User, Depends(get_current_active_user)],
    news_service: Annotated[NewsService, Depends(get_news_service)],
):
    """Retrieve a list of all news sources configured by the current user."""
    try:
        sources = await news_service.get_all_sources(user_id=current_user.id)
        return sources
    except Exception as e:
        logger.exception("Failed to retrieve user news sources", exc_info=True)
        raise HTTPException(status_code=500, detail="Error retrieving news sources.")


@router.get(
    "/sources/category/{category_id}",
    response_model=List[NewsSource],
    summary="List user's news sources by category",
)
async def get_sources_by_category(
    category_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    news_service: Annotated[NewsService, Depends(get_news_service)],
):
    """Retrieve news sources for the current user belonging to a specific category."""
    try:
        # Verify category exists for user first
        category = await news_service.get_category_by_id(
            category_id=category_id, user_id=current_user.id
        )
        if not category:
            raise HTTPException(
                status_code=404,
                detail=f"Category {category_id} not found or not owned by user.",
            )

        sources = await news_service.get_sources_by_category_id(
            category_id=category_id, user_id=current_user.id
        )
        return sources
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            f"Failed to retrieve sources for category {category_id}", exc_info=True
        )
        raise HTTPException(
            status_code=500, detail="Error retrieving category sources."
        )


@router.get(
    "/sources/{source_id}",
    response_model=NewsSource,
    summary="Get a specific news source",
)
async def get_news_source_by_id(
    source_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    news_service: Annotated[NewsService, Depends(get_news_service)],
):
    """Retrieve a single news source by ID, ensuring it belongs to the current user."""
    source = await news_service.get_source_by_id(
        source_id=source_id, user_id=current_user.id
    )
    if not source:
        raise HTTPException(
            status_code=404,
            detail=f"News source {source_id} not found or not owned by user.",
        )
    return source


@router.post(
    "/sources",
    response_model=NewsSource,
    status_code=status.HTTP_201_CREATED,
    summary="Create a news source",
)
async def create_news_source(
    source_data: NewsSourceCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    news_service: Annotated[NewsService, Depends(get_news_service)],
):
    """Create a new news source configuration for the current user."""
    # Ensure the source data is associated with the current user
    source_data_with_user = source_data.model_copy(update={"user_id": current_user.id})

    try:
        created_source = await news_service.create_source(
            source_data=source_data_with_user, user_id=current_user.id
        )
        if not created_source:
            # Service method handles checks for existing name/url for the user
            # Re-check here to provide specific conflict error
            name = source_data_with_user.name.strip()
            url = str(source_data_with_user.url).strip()
            if await news_service._source_repo.exists_by_name(name, current_user.id):
                raise HTTPException(
                    status_code=409, detail=f"Source name '{name}' already exists."
                )
            elif await news_service._source_repo.exists_by_url(url, current_user.id):
                raise HTTPException(
                    status_code=409, detail=f"Source URL '{url}' already exists."
                )
            elif not await news_service.get_category_by_id(
                source_data_with_user.category_id, current_user.id
            ):
                raise HTTPException(
                    status_code=400,
                    detail=f"Category ID {source_data_with_user.category_id} not found or not owned by user.",
                )
            else:
                raise HTTPException(
                    status_code=500, detail="Failed to create news source."
                )
        return created_source
    except ValueError as ve:  # Catch validation errors from service
        logger.error(f"Source creation validation error: {ve}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to create news source", exc_info=True)
        raise HTTPException(status_code=500, detail="Error creating news source.")


@router.put(
    "/sources/{source_id}",
    response_model=NewsSource,
    summary="Update a news source",
)
async def update_news_source(
    source_id: int,
    source_data: NewsSourceUpdate,  # Allows partial updates
    current_user: Annotated[User, Depends(get_current_active_user)],
    news_service: Annotated[NewsService, Depends(get_news_service)],
):
    """Update an existing news source configuration for the current user."""
    try:
        # Check if source exists for user first
        existing_source = await news_service.get_source_by_id(
            source_id=source_id, user_id=current_user.id
        )
        if not existing_source:
            raise HTTPException(
                status_code=404,
                detail=f"News source {source_id} not found or not owned by user.",
            )

        source_data_dict = source_data.model_dump(exclude_unset=True)
        if not source_data_dict:
            raise HTTPException(status_code=400, detail="No update data provided.")

        # Prepare full data for service update method (which expects name, url, category_name)
        # Use existing values if not provided in update
        name = source_data_dict.get("name", existing_source["name"])
        url = str(source_data_dict.get("url", existing_source["url"]))
        category_id = source_data_dict.get(
            "category_id", existing_source["category_id"]
        )

        # Fetch category name for the service method
        category = await news_service.get_category_by_id(
            category_id=category_id, user_id=current_user.id
        )
        if not category:
            raise HTTPException(
                status_code=400,
                detail=f"Category ID {category_id} not found or not owned by user.",
            )
        category_name = category["name"]

        # Perform checks for name/url conflicts if they are being changed
        if "name" in source_data_dict and name != existing_source["name"]:
            if await news_service._source_repo.exists_by_name(name, current_user.id):
                raise HTTPException(
                    status_code=409, detail=f"Source name '{name}' already exists."
                )
        if "url" in source_data_dict and url != existing_source["url"]:
            if await news_service._source_repo.exists_by_url(url, current_user.id):
                raise HTTPException(
                    status_code=409, detail=f"Source URL '{url}' already exists."
                )

        # Call the service update method
        success = await news_service.update_source(
            source_id=source_id,
            user_id=current_user.id,
            name=name,
            url=url,
            category_name=category_name,  # Service expects category name
        )

        if not success:
            # Should have been caught by checks above or repo error
            raise HTTPException(status_code=500, detail="Failed to update news source.")

        # Return the updated source
        updated_source_data = await news_service.get_source_by_id(
            source_id, current_user.id
        )
        return updated_source_data

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update news source {source_id}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error updating news source.")


@router.delete(
    "/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a news source",
)
async def delete_news_source(
    source_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    news_service: Annotated[NewsService, Depends(get_news_service)],
):
    """Delete a news source configuration belonging to the current user."""
    success = await news_service.delete_source(
        source_id=source_id, user_id=current_user.id
    )
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"News source {source_id} not found or not owned by user.",
        )
    return None


# --- News Category Endpoints (User-Aware) ---


@router.get(
    "/categories",
    response_model=List[NewsCategory],
    summary="List user's news categories",
)
async def get_all_news_categories(
    current_user: Annotated[User, Depends(get_current_active_user)],
    news_service: Annotated[NewsService, Depends(get_news_service)],
):
    """Retrieve a list of all news categories created by the current user."""
    try:
        # Use the method that includes source counts
        categories = await news_service.get_all_categories_with_counts(
            user_id=current_user.id
        )
        return categories
    except Exception as e:
        logger.exception("Failed to retrieve user news categories", exc_info=True)
        raise HTTPException(status_code=500, detail="Error retrieving news categories.")


@router.post(
    "/categories",
    response_model=NewsCategory,
    status_code=status.HTTP_201_CREATED,
    summary="Create a news category",
)
async def create_news_category(
    category_data: NewsCategoryCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    news_service: Annotated[NewsService, Depends(get_news_service)],
):
    """Create a new news category for the current user."""
    # Ensure the category data is associated with the current user
    category_data_with_user = category_data.model_copy(
        update={"user_id": current_user.id}
    )

    try:
        created_category = await news_service.create_category(
            category_data=category_data_with_user, user_id=current_user.id
        )
        if not created_category:
            # Service method handles checks for existing name for the user
            name = category_data_with_user.name.strip()
            if await news_service._category_repo.exists_by_name(name, current_user.id):
                raise HTTPException(
                    status_code=409, detail=f"Category name '{name}' already exists."
                )
            else:
                raise HTTPException(
                    status_code=500, detail="Failed to create news category."
                )
        # Need to fetch the full category object including potential source_count
        # Service create_category returns dict with id, name, user_id. Fetch full object.
        full_category = await news_service.get_category_by_id(
            created_category["id"], current_user.id
        )
        # Add source_count manually if needed, or adjust response model/service method
        full_category_dict = dict(full_category) if full_category else {}
        full_category_dict["source_count"] = 0  # Assume 0 for newly created
        return full_category_dict

    except ValueError as ve:  # Catch validation errors from service
        logger.error(f"Category creation validation error: {ve}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to create news category", exc_info=True)
        raise HTTPException(status_code=500, detail="Error creating news category.")


@router.put(
    "/categories/{category_id}",
    response_model=NewsCategory,
    summary="Update a news category",
)
async def update_news_category(
    category_id: int,
    category_data: NewsCategoryUpdate,  # Allows partial updates (only name)
    current_user: Annotated[User, Depends(get_current_active_user)],
    news_service: Annotated[NewsService, Depends(get_news_service)],
):
    """Update an existing news category's name for the current user."""
    try:
        category_data_dict = category_data.model_dump(exclude_unset=True)
        new_name = category_data_dict.get("name", "").strip()
        if not new_name:
            raise HTTPException(
                status_code=400, detail="Category name cannot be empty."
            )

        # Check for duplicate name for this user
        existing_category = await news_service.get_category_by_id(
            category_id, current_user.id
        )
        if not existing_category:
            raise HTTPException(
                status_code=404,
                detail=f"Category {category_id} not found or not owned by user.",
            )

        if new_name != existing_category["name"]:
            if await news_service._category_repo.exists_by_name(
                new_name, current_user.id
            ):
                raise HTTPException(
                    status_code=409,
                    detail=f"Category name '{new_name}' already exists.",
                )

        success = await news_service.update_category(
            category_id=category_id, user_id=current_user.id, new_name=new_name
        )
        if not success:
            # Should have been caught by checks above or repo error
            raise HTTPException(
                status_code=500, detail="Failed to update news category."
            )

        # Return the updated category, potentially with source count
        updated_category = await news_service.get_category_by_id(
            category_id, current_user.id
        )
        # Fetch count separately or adjust service/response model
        count_data = await news_service.get_all_categories_with_counts(current_user.id)
        source_count = next(
            (c["source_count"] for c in count_data if c["id"] == category_id), 0
        )
        updated_category_dict = dict(updated_category) if updated_category else {}
        updated_category_dict["source_count"] = source_count
        return updated_category_dict

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update news category {category_id}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error updating news category.")


@router.delete(
    "/categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a news category",
)
async def delete_news_category(
    category_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    news_service: Annotated[NewsService, Depends(get_news_service)],
):
    """Delete a news category belonging to the current user."""
    # Service method handles user check and potential FK constraints
    success = await news_service.delete_category(
        category_id=category_id, user_id=current_user.id
    )
    if not success:
        # Could be 404 (not found/owned) or 409 (conflict due to sources)
        # Check existence first for better error
        if await news_service.get_category_by_id(category_id, current_user.id) is None:
            raise HTTPException(
                status_code=404,
                detail=f"Category {category_id} not found or not owned by user.",
            )
        else:
            # Assume conflict if deletion failed but category exists
            raise HTTPException(
                status_code=409,
                detail=f"Cannot delete category {category_id} as it may have associated news sources.",
            )
    return None


# --- News Fetching and Processing Endpoints (User-Aware) ---

# Note: fetch_single_url is removed as it wasn't user-aware and less practical.


@router.post(
    "/tasks/fetch/batch",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start fetching news from user's sources",
    response_model=Dict[str, str],
)
async def trigger_fetch_batch_sources(
    request: FetchSourceBatchRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    news_service: Annotated[NewsService, Depends(get_news_service)],
):
    """
    Start Celery tasks to fetch news from multiple sources belonging to the current user.
    """
    try:
        if not request.source_ids:
            raise HTTPException(status_code=400, detail="No source IDs provided.")

        # Validate that all source IDs belong to the user before scheduling
        valid_source_ids = []
        for source_id in request.source_ids:
            source = await news_service.get_source_by_id(
                source_id=source_id, user_id=current_user.id
            )
            if not source:
                logger.warning(
                    f"Skipping source ID {source_id} in batch fetch request for user {current_user.id} as it's not found or not owned."
                )
                # Optionally raise error, or just skip non-owned sources
                # raise HTTPException(status_code=403, detail=f"Source ID {source_id} not owned by user.")
            else:
                valid_source_ids.append(source_id)

        if not valid_source_ids:
            raise HTTPException(
                status_code=400,
                detail="None of the provided source IDs belong to the user.",
            )

        task_group_id = str(uuid.uuid4())
        result = await news_service.fetch_sources_in_background(
            source_ids=valid_source_ids,
            user_id=current_user.id,  # Pass user_id
            task_group_id=task_group_id,
        )

        logger.info(
            f"Scheduled Celery tasks for {len(valid_source_ids)} sources for user {current_user.id} with task_group_id: {task_group_id}"
        )
        return {
            "task_group_id": task_group_id,
            "message": f"Fetch tasks scheduled for {len(valid_source_ids)} sources.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error scheduling batch source fetch", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to schedule batch fetch: {str(e)}"
        )


# --- News Analysis Endpoints (User-Aware) ---

# Note: analyze_all_news_background needs modification in service to be user-specific
# Assuming it's modified or removed for now.


@router.post(
    "/tasks/analyze/items",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start analysis for specific user news items",
    response_model=Dict[str, str],
)
async def trigger_analyze_news_by_ids(
    request: AnalyzeRequest,  # Contains news_ids and force flag
    current_user: Annotated[User, Depends(get_current_active_user)],
    news_service: Annotated[NewsService, Depends(get_news_service)],
):
    """
    Start a background task to analyze specific news items belonging to the current user.
    """
    try:
        news_ids = request.news_ids
        force_reanalysis = request.force or False  # Use force from request

        if not news_ids:
            raise HTTPException(status_code=400, detail="No news items specified.")

        # Validate that all news IDs exist and belong to the user
        valid_news_ids = []
        for news_id in news_ids:
            item = await news_service.get_news_by_id(
                news_id=news_id, user_id=current_user.id
            )
            if not item:
                logger.warning(
                    f"Skipping news ID {news_id} in analysis request for user {current_user.id} as it's not found or not owned."
                )
                # Optionally raise error
            else:
                valid_news_ids.append(news_id)

        if not valid_news_ids:
            raise HTTPException(
                status_code=400,
                detail="None of the provided news IDs belong to the user.",
            )

        # Assuming service method analyze_news_by_ids_background exists and takes user_id
        # await news_service.analyze_news_by_ids_background(valid_news_ids, current_user.id, force_reanalysis)

        # Placeholder: Raise 501 as background task logic needs user context update
        raise HTTPException(
            status_code=501,
            detail="Background analysis by IDs not implemented with user context.",
        )

        # num_items = len(valid_news_ids)
        # return {"message": f"Analysis started for {num_items} news item{'s' if num_items != 1 else ''}."}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to start analysis for specific items", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to start analysis.")


@router.post(
    "/analyze/content",
    summary="Analyze provided content with instructions",
    response_class=StreamingResponse,
    description="Analyze arbitrary text content using the LLM based on provided instructions. The result is streamed. (Not user-specific unless results are saved per user)",
)
async def analyze_arbitrary_content(
    request: AnalyzeContentRequest,
    # current_user: Annotated[User, Depends(get_current_active_user)], # Add if saving results per user
    news_service: Annotated[NewsService, Depends(get_news_service)],
):
    """Analyze arbitrary text content using the LLM. (Currently not user-specific)."""
    try:
        if not request.content or not request.content.strip():
            raise HTTPException(status_code=400, detail="Content cannot be empty.")
        if not request.instructions or not request.instructions.strip():
            raise HTTPException(status_code=400, detail="Instructions cannot be empty.")

        # Assuming analyze_content_streaming doesn't need user_id unless saving results
        async def stream_generator():
            # Need to await the coroutine returned by the service method
            stream = await news_service.analyze_content_streaming(
                content=request.content, instructions=request.instructions
            )
            async for chunk in stream:
                yield f"{chunk}"

        return StreamingResponse(stream_generator(), media_type="text/plain")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to analyze content", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Error analyzing content: {str(e)}"
        )


@router.post(
    "/items/{news_id}/analyze/stream",
    summary="Stream analysis for a specific user news item",
    description="Streams analysis for a news item belonging to the current user.",
    response_class=StreamingResponse,
)
async def stream_news_item_analysis(
    news_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    news_service: Annotated[
        NewsService, Depends(get_news_service)
    ],  # Moved Depends before Query
    force: bool = Query(False, description="Force re-analysis"),
):
    """Streams analysis for a specific news item belonging to the current user."""
    # Service method now handles user check
    return StreamingResponse(
        news_service.stream_analysis_for_news_item(
            news_id=news_id, user_id=current_user.id, force=force
        ),
        media_type="text/plain",
    )
