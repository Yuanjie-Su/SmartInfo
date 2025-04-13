// temp/frontend/src/types/qa.ts
// Aligned with backend/api/schemas/qa.py and backend/api/websockets/qa_ws.py

/**
 * Represents a single entry in the Q&A history.
 * Matches backend schema: QAHistory
 */
export interface QAHistory {
    id: number;
    question: string;
    answer: string;
    context_ids?: string | null; // Stored as TEXT (likely JSON string) in backend
    created_date: string;      // Stored as TEXT in backend
}

/**
 * Represents the request body for asking a question (non-streaming or streaming).
 * Matches relevant fields in backend schemas: QARequest (for non-streaming), WebSocket command 'ask_question' payload.
 */
export interface QARequest {
    question: string;
    // Add other fields if needed based on specific endpoint requirements
    // e.g., context_ids: string[]; use_history: boolean;
}

/**
 * Represents the response body for a non-streaming QA request.
 * Matches backend schema: QAResponse
 */
export interface QAResponse {
    answer: string;
    error?: string | null;
}

/**
 * Represents a progress update message sent via WebSocket during streaming Q&A.
 * Matches backend schema: QAProgressUpdate
 */
export interface QAProgressUpdate {
    operation: string; // e.g., "qa"
    status: 'in_progress' | 'completed' | 'failed'; // Matches backend status strings
    message?: string | null;
    partial_answer?: string | null;
    error?: string | null;
}

/**
 * Represents the different types of messages received over the QA WebSocket.
 * Matches messages sent from backend/api/websockets/qa_ws.py
 */
export type QAWebSocketMessage =
    | { type: 'connection_established', client_id: string }
    | { type: 'qa_stream', data: QAProgressUpdate }
    | { type: 'qa_complete', data: QAProgressUpdate } // Final answer/status included here
    | { type: 'qa_error', data: QAProgressUpdate } // Specific error during QA process
    | { type: 'qa_history', data: QAHistory[] }
    | { type: 'error', message: string }; // General connection/command errors