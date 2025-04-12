export interface QARequest {
    question: string;
    sources?: string[];
}

export interface QAProgressUpdate {
    partial_answer?: string;
    status: 'in_progress' | 'completed' | 'failed';
    message?: string;
}

export interface QAHistoryItem {
    id: string;
    question: string;
    answer: string;
    sources: string[];
    created_at: string;
}

export type QAWebSocketMessage =
    | { type: 'qa_stream', data: QAProgressUpdate }
    | { type: 'qa_complete' }; 