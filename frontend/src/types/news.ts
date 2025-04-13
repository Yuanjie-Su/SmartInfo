// temp/frontend/src/types/news.ts
// Aligned with backend/api/schemas/news.py and backend/api/websockets/news_ws.py

/**
 * Represents a single news item fetched from the database.
 * Matches backend schema: NewsItem
 */
export interface NewsItem {
    id: number;
    title: string;
    link: string;
    source_name: string;
    category_name: string;
    source_id?: number | null;
    category_id?: number | null;
    summary?: string | null;
    analysis?: string | null;
    date?: string | null; // Stored as TEXT in backend
}

/**
 * Represents a news category.
 * Matches backend schema: NewsCategory
 */
export interface NewsCategory {
    id: number;
    name: string;
}

/**
 * Represents a news category with source count.
 * Matches backend schema: NewsCategoryWithCount
 */
export interface NewsCategoryWithCount extends NewsCategory {
    source_count: number;
}

/**
 * Represents a news source.
 * Matches backend schema: NewsSource
 */
export interface NewsSource {
    id: number;
    name: string;
    url: string;
    category_id: number;
    category_name: string;
}

/**
 * Represents the request body for creating a news source.
 * Matches backend schema: NewsSourceCreate
 */
export interface NewsSourceCreate {
    name: string;
    url: string;
    category_name: string;
}

/**
 * Represents the request body for updating a news source.
 * Matches backend schema: NewsSourceUpdate
 */
export interface NewsSourceUpdate {
    name?: string | null;
    url?: string | null;
    category_name?: string | null;
}

/**
 * Represents the request body for creating a news category.
 * Matches backend schema: NewsCategoryCreate
 */
export interface NewsCategoryCreate {
    name: string;
}

/**
 * Represents the request body for updating a news category.
 * Matches backend schema: NewsCategoryUpdate
 */
export interface NewsCategoryUpdate {
    name: string;
}


/**
 * Represents the request body for triggering the news fetching process.
 * Matches backend schema: FetchNewsRequest
 */
export interface FetchNewsRequest {
    source_ids?: number[] | null; // List of source IDs or null/undefined for all
}

/**
 * Represents a progress update message for a single URL during news fetching.
 * Matches backend schema: NewsProgressUpdate (used in WS callback)
 */
export interface NewsFetchProgressUpdate {
    url: string;
    status: string; // e.g., "Crawling", "Crawled - Success", "Extracting (LLM)", "Saving", "Complete", "Error", "Skipped"
    details: string; // e.g., "Checking token size (1234)", "Saved 5, Skipped 0", "Extraction Failed: API Error"
}

/**
 * Represents a chunk of raw stream data (e.g., from LLM analysis).
 * Matches backend schema: StreamChunkUpdate (used in WS callback)
 */
export interface NewsStreamChunkUpdate {
    // Note: Backend sends type="stream_chunk" outside this object in the wrapper message
    chunk: string;
}

/**
 * Represents the different types of messages received over the News Progress WebSocket.
 * Matches messages broadcasted from backend/api/routers/news_router.py via connection_manager
 */
export type NewsWebSocketMessage =
    | { type: 'connection_established', client_id: string }
    | { type: 'news_progress', data: NewsFetchProgressUpdate } // Matches backend structure
    | { type: 'stream_chunk', data: NewsStreamChunkUpdate }   // Matches backend structure
    | { type: 'error', message: string }; // General connection errors