# backend/api/routers/qa_router.py
"""
REST API endpoints for QA-related operations (non-streaming).
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query

# Local project imports
from backend.services.qa_service import QAService
from backend.api.dependencies import get_qa_service
from backend.api.schemas.qa import QAHistory, QARequest, QAResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/history", response_model=List[QAHistory])
async def get_qa_history(
    limit: int = Query(50, ge=1, le=1000, description="Number of items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    qa_service: QAService = Depends(get_qa_service)
):
    """Get QA history with pagination."""
    try:
        # Assuming service returns List[QAHistory] or compatible Dicts
        history_data = await qa_service.get_qa_history(limit=limit, offset=offset) # Use the sync method name from service
        # Map to schema if needed (assuming service returns list of dicts)
        return [QAHistory.model_validate(item) for item in history_data]
    except Exception as e:
        logger.error(f"Error fetching QA history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error fetching QA history")

@router.get("/history/{qa_id}", response_model=QAHistory)
async def get_qa_history_item(
    qa_id: int,
    qa_service: QAService = Depends(get_qa_service)
):
    """Get a specific QA history item by ID."""
    # Assumes get_qa_history_item exists in service and returns QAHistory or None
    item = await qa_service.get_qa_history_item(qa_id)
    if not item:
        raise HTTPException(status_code=404, detail="QA history item not found")
    # Assuming service returns dict, validate with model
    return QAHistory.model_validate(item)


@router.post("/ask", response_model=QAResponse)
async def ask_question_non_streaming(
    request: QARequest,
    qa_service: QAService = Depends(get_qa_service)
):
    """
    Ask a question and get a non-streaming response.
    For streaming responses, use the WebSocket endpoint '/ws/qa'.
    """
    try:
        # Call the non-streaming service method
        result_dict = await qa_service.answer_question_non_streaming(
            question=request.question
        ) # Pass only the question for simple non-streaming

        # Check for errors returned by the service
        if result_dict.get("error"):
             # Determine appropriate status code based on error type if possible
             status_code = 400 if "empty" in result_dict["error"].lower() else 500
             raise HTTPException(status_code=status_code, detail=result_dict["error"])

        # Create response object from the successful result
        if "answer" in result_dict:
            return QAResponse(answer=result_dict["answer"], error=None)
        else:
             # Should not happen if error handling above is correct
             logger.error(f"Non-streaming QA for '{request.question}' returned unexpected dict: {result_dict}")
             raise HTTPException(status_code=500, detail="Internal server error: Invalid response from QA service.")

    except HTTPException as http_exc:
        raise http_exc # Re-raise FastAPI exceptions
    except Exception as e:
        logger.error(f"Error processing non-streaming QA request: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error during question answering.")


@router.delete("/history/{qa_id}", status_code=204)
async def delete_qa_history_item(
    qa_id: int,
    qa_service: QAService = Depends(get_qa_service)
):
    """Delete a specific QA history item."""
    success = await qa_service.delete_qa_entry(qa_id) # Use the correct service method name
    if not success:
        raise HTTPException(status_code=404, detail="QA history item not found")
    return None


@router.delete("/history", status_code=200)
async def clear_qa_history(
    qa_service: QAService = Depends(get_qa_service)
):
    """Clear all QA history."""
    success = await qa_service.clear_qa_history() # Use the correct service method name
    if success:
        return {"message": "QA history cleared successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to clear QA history.")