# backend/api/routers/news_router.py
"""
REST API endpoints for news-related operations.
"""

import asyncio
import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Body, BackgroundTasks

# Local project imports
from backend.services.news_service import NewsService
from backend.api.dependencies import get_news_service
from backend.api.schemas.news import (
    NewsSource, NewsCategory, NewsCategoryWithCount, NewsItem,
    NewsSourceCreate, NewsSourceUpdate, NewsCategoryCreate,
    NewsCategoryUpdate, FetchNewsRequest, NewsSearchRequest,
    NewsProgressUpdate, StreamChunkUpdate # Import schemas for callbacks
)
from backend.api.websockets.connection_manager import connection_manager # Import for callbacks

router = APIRouter()
logger = logging.getLogger(__name__)

# --- Helper Function (Consider moving to service if complex) ---
async def _get_category_id_or_create(category_name: str, news_service: NewsService) -> int:
    """Gets category ID by name, creates it if not found."""
    category_id = await news_service.get_category_id_by_name(category_name) # Assumes service method exists
    if category_id:
        return category_id
    else:
        # Create category if it doesn't exist
        new_id = await news_service.add_category(category_name) # Assumes service method exists
        if new_id:
            return new_id
        else:
            # Log the error in the service layer ideally
            logger.error(f"Failed to get or create category '{category_name}' via service.")
            raise HTTPException(status_code=500, detail=f"Failed to process category '{category_name}'")

# --- Sources ---
@router.get("/sources", response_model=List[NewsSource])
async def get_sources(
    category_id: Optional[int] = Query(None, description="Filter by category ID"),
    news_service: NewsService = Depends(get_news_service)
):
    """Get all news sources, optionally filtered by category ID."""
    try:
        if category_id:
            # Assuming service returns list matching schema or requires mapping
            sources_data = await news_service.get_sources_by_category_id(category_id) # Assume service handles this
            # If service returns basic dicts, validate/map here (though ideally service returns schema models)
            # return [NewsSource.model_validate(s) for s in sources_data]
            return sources_data # Assuming service returns List[NewsSource] or compatible List[Dict]
        else:
            return await news_service.get_all_sources() # Assume service returns List[NewsSource]
    except Exception as e:
        logger.error(f"Error fetching sources: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error fetching sources")


@router.get("/sources/{source_id}", response_model=NewsSource)
async def get_source(
    source_id: int,
    news_service: NewsService = Depends(get_news_service)
):
    """Get a specific news source by ID."""
    source = await news_service.get_source_by_id(source_id) # Assume service method exists and returns NewsSource or None
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.post("/sources", response_model=NewsSource, status_code=201)
async def create_source(
    source_create: NewsSourceCreate,
    news_service: NewsService = Depends(get_news_service)
):
    """Create a new news source."""
    try:
        # Service method should handle category lookup/creation internally
        created_source = await news_service.add_source(
            name=source_create.name,
            url=source_create.url,
            category_name=source_create.category_name
        ) # Assume service returns the created NewsSource object or raises error
        if created_source is None:
             # Should not happen if service raises exceptions for failures
             raise HTTPException(status_code=400, detail="Failed to create source (check logs or duplicate URL).")
        return created_source
    except ValueError as ve: # Example: Catch specific error from service for duplicates
        raise HTTPException(status_code=409, detail=str(ve))
    except Exception as e:
        logger.error(f"Error creating source: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error creating source.")


@router.put("/sources/{source_id}", response_model=NewsSource)
async def update_source(
    source_id: int,
    source_update: NewsSourceUpdate, # Use the dedicated update schema
    news_service: NewsService = Depends(get_news_service)
):
    """Update an existing news source."""
    try:
        # Pass the partial update data to the service
        # The service should fetch the existing item, apply changes, and save
        updated_source = await news_service.update_source(
            source_id=source_id,
            update_data=source_update # Pass the Pydantic model directly
        ) # Assume service returns the updated NewsSource object or raises error
        if updated_source is None:
             # Service should raise specific errors for not found or update failure
             raise HTTPException(status_code=404, detail="Source not found or update failed.")
        return updated_source
    except ValueError as ve: # Example: Catch specific error from service (e.g., not found)
         raise HTTPException(status_code=404, detail=str(ve)) # Or 400/409 depending on error
    except Exception as e:
        logger.error(f"Error updating source {source_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error updating source.")


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(
    source_id: int,
    news_service: NewsService = Depends(get_news_service)
):
    """Delete a news source."""
    success = await news_service.delete_source(source_id) # Assume service returns bool
    if not success:
        raise HTTPException(status_code=404, detail="Source not found")
    return None # Return No Content


@router.get("/categories/{category_id}", response_model=NewsCategory)
async def get_category(
    category_id: int,
    news_service: NewsService = Depends(get_news_service)
):
    """Get a specific news category by ID."""
    category = await news_service.get_category_by_id(category_id) # Assume service method exists
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@router.post("/categories", response_model=NewsCategory, status_code=201)
async def create_category(
    category_create: NewsCategoryCreate,
    news_service: NewsService = Depends(get_news_service)
):
    """Create a new news category."""
    try:
        created_category = await news_service.add_category(name=category_create.name) # Assume service handles duplicates and returns created object or raises error
        if created_category is None:
             raise HTTPException(status_code=400, detail="Failed to create category (check logs or duplicate name).")
        return created_category
    except ValueError as ve: # Example: Catch duplicate name error from service
        raise HTTPException(status_code=409, detail=str(ve))
    except Exception as e:
        logger.error(f"Error creating category: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error creating category.")


@router.put("/categories/{category_id}", response_model=NewsCategory)
async def update_category(
    category_id: int,
    category_update: NewsCategoryUpdate,
    news_service: NewsService = Depends(get_news_service)
):
    """Update an existing news category's name."""
    try:
        updated_category = await news_service.update_category(
            category_id=category_id,
            new_name=category_update.name
        ) # Assume service returns updated object or raises error
        if updated_category is None:
            raise HTTPException(status_code=404, detail="Category not found or update failed (check logs or duplicate name).")
        return updated_category
    except ValueError as ve: # Example: Catch specific error from service (e.g., not found, duplicate name)
         status_code = 409 if "duplicate" in str(ve).lower() else 404
         raise HTTPException(status_code=status_code, detail=str(ve))
    except Exception as e:
        logger.error(f"Error updating category {category_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error updating category.")


@router.delete("/categories/{category_id}", status_code=204)
async def delete_category(
    category_id: int,
    news_service: NewsService = Depends(get_news_service)
):
    """Delete a news category and associated sources (via cascade)."""
    success = await news_service.delete_category(category_id)
    if not success:
        raise HTTPException(status_code=404, detail="Category not found")
    return None


# --- News Items ---
@router.get("/items", response_model=List[NewsItem])
async def get_news(
    limit: int = Query(50, ge=1, le=1000, description="Number of items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    news_service: NewsService = Depends(get_news_service)
):
    """Get news items with pagination."""
    try:
        # Assuming service returns List[NewsItem] or compatible
        return await news_service.get_all_news(limit=limit, offset=offset)
    except Exception as e:
         logger.error(f"Error fetching news items: {e}", exc_info=True)
         raise HTTPException(status_code=500, detail="Internal server error fetching news items")


@router.get("/items/{item_id}", response_model=NewsItem)
async def get_news_item(
    item_id: int,
    news_service: NewsService = Depends(get_news_service)
):
    """Get a specific news item by ID."""
    item = await news_service.get_news_by_id(item_id) # Assume service returns NewsItem or None
    if not item:
        raise HTTPException(status_code=404, detail="News item not found")
    return item


@router.delete("/items/{item_id}", status_code=204)
async def delete_news_item(
    item_id: int,
    news_service: NewsService = Depends(get_news_service)
):
    """Delete a news item."""
    success = await news_service.delete_news(item_id)
    if not success:
        raise HTTPException(status_code=404, detail="News item not found")
    return None


@router.delete("/items", status_code=200)
async def clear_news(
    news_service: NewsService = Depends(get_news_service)
):
    """Clear all news items."""
    success = await news_service.clear_all_news()
    if success:
        return {"message": "All news items cleared successfully"}
    else:
         raise HTTPException(status_code=500, detail="Failed to clear news items.")


# --- Search (Placeholder - Requires Service Implementation) ---
@router.post("/search", response_model=List[NewsItem])
async def search_news(
    search_request: NewsSearchRequest, # Renamed variable for clarity
    news_service: NewsService = Depends(get_news_service)
):
    """Search for news items (Placeholder - requires service implementation)."""
    logger.warning("'/news/search' endpoint called but search logic is not implemented in the service layer.")
    # result = await news_service.search_news(query=search_request.query, ...)
    # return result
    # For now, return empty or 501
    # raise HTTPException(status_code=501, detail="Search functionality not implemented")
    return []


# --- Fetch News (Triggers async process) ---
@router.post("/fetch", status_code=202) # 202 Accepted
async def trigger_fetch_news(
    request: FetchNewsRequest,
    background_tasks: BackgroundTasks, # Use FastAPI BackgroundTasks
    news_service: NewsService = Depends(get_news_service)
):
    """
    Trigger asynchronous news fetching from selected sources.
    Progress updates are sent via the '/ws/news_progress' WebSocket.
    """
    logger.info(f"Received request to fetch news for sources: {request.source_ids or 'All'}")

    # Define the callback handlers that will interact with the WebSocket manager
    async def send_ws_progress(url: str, status: str, details: str):
        """Callback to send structured progress updates."""
        try:
             update = NewsProgressUpdate(url=url, status=status, details=details)
             await connection_manager.broadcast_to_group(
                 {"type": "news_progress", "data": update.model_dump()},
                 "news_fetch_progress" # Specific group for fetch progress
             )
        except Exception as ws_err:
             logger.error(f"WS Callback Error (Progress): {ws_err}", exc_info=True)

    async def send_ws_stream_chunk(chunk: str):
        """Callback to send raw LLM stream chunks."""
        try:
            update = StreamChunkUpdate(chunk=chunk)
            await connection_manager.broadcast_to_group(
                 {"type": "stream_chunk", "data": update.model_dump()},
                 "news_fetch_progress" # Send to the same group
             )
        except Exception as ws_err:
             logger.error(f"WS Callback Error (Stream Chunk): {ws_err}", exc_info=True)

    # Add the service call to FastAPI's background tasks
    # This ensures the HTTP response returns quickly
    background_tasks.add_task(
        news_service.fetch_news_from_sources, # The coroutine to run
        source_ids=request.source_ids,
        on_url_status_update=send_ws_progress, # Pass the async callback function
        on_stream_chunk_update=send_ws_stream_chunk, # Pass the async callback function
    )

    return {"message": "News fetching process initiated in background. Connect to the '/ws/news_progress' WebSocket for updates."}

# Note: The actual WebSocket endpoint definition `/ws/news_progress` should be moved
# to a file under `api/websockets/`, for example `api/websockets/progress_ws.py`.
# Ensure `connection_manager` is properly initialized and accessible there.