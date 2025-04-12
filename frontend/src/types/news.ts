export interface NewsItem {
    id: string;
    title: string;
    url: string;
    source: string;
    category: string;
    published_at: string;
    content: string;
    summary: string;
    analysis: string;
    created_at: string;
    updated_at: string;
}

export interface FetchNewsRequest {
    category?: string;
    source?: string;
    limit?: number;
}

export interface NewsProgressUpdate {
    total_tasks: number;
    completed_tasks: number;
    current_stage: string;
    message: string;
    status: 'in_progress' | 'completed' | 'failed';
}

export type NewsAnalysisChunk = string;

export type NewsWebSocketMessage =
    | { type: 'news_progress', data: NewsProgressUpdate }
    | { type: 'news_analysis_chunk', data: NewsAnalysisChunk }; 