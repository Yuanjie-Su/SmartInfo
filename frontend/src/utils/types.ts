// News Category Types
export interface NewsCategory {
  id: number;
  name: string;
  source_count?: number;
}

export interface NewsCategoryCreate {
  name: string;
}

export interface NewsCategoryUpdate {
  name: string;
}

// News Source Types
export interface NewsSource {
  id: number;
  name: string;
  url: string;
  category_id: number;
  category_name?: string;
}

export interface NewsSourceCreate {
  name: string;
  url: string;
  category_id: number;
}

export interface NewsSourceUpdate {
  name?: string;
  url?: string;
  category_id?: number;
}

// News Types
export interface NewsItem {
  id: number;
  title: string;
  url: string;
  source_id?: number;
  category_id?: number;
  summary?: string;
  content?: string;
  analysis?: string;
  date?: string;
  source_name?: string;
  category_name?: string;
}

export interface NewsItemCreate {
  title: string;
  url: string;
  source_id?: number;
  category_id?: number;
  summary?: string;
  content?: string;
  should_analyze?: boolean;
}

export interface NewsItemUpdate {
  title?: string;
  source_id?: number;
  category_id?: number;
  summary?: string;
  content?: string;
  analysis?: string;
  date?: string;
}

export interface NewsFilterParams {
  category_id?: number;
  source_id?: number;
  analyzed?: boolean;
  page?: number;
  page_size?: number;
  search_term?: string;
}

// Task Types for News Fetching
export interface FetchTaskItem {
  sourceId: number;       // Source ID
  sourceName: string;     // Source Name
  status: 'pending' | 'fetching' | 'processing' | 'crawling' | 'analyzing' | 'saving' | 'complete' | 'error' | 'initializing';
  progress?: number;     //  Progress percentage (0-100)
  message?: string;      //  For displaying error messages
  items_saved?: number;  // Add this based on backend message format
}

export interface FetchTaskResponse {
  task_group_id: string;
  message: string;
}

export interface UpdateAnalysisRequest {
  task_group_id: string;
  analysis: string;
}

export interface AnalyzeRequest {
  news_ids?: number[];
  force?: boolean;
}

export interface FetchSourceRequest {
  source_id: number;
}

export interface FetchUrlRequest {
  url: string;
  source_id?: number;
  should_analyze?: boolean;
}

export interface AnalyzeContentRequest {
  content: string;
  instructions: string;
}

// API Key Types
export interface ApiKey {
  id: number;
  model: string;
  base_url: string;
  api_key: string;
  context: number;
  max_output_tokens: number;
  description?: string;
  created_date?: string; // ISO 8601 string
  modified_date?: string; // ISO 8601 string
}

export interface ApiKeyCreate {
  model: string;
  base_url: string;
  api_key: string;
  context: number;
  max_output_tokens: number;
  description?: string;
}

// System Config Types
export interface SystemConfigUpdate {
  settings: Record<string, any>;
}

// Chat Types
export interface Chat {
  id: number;
  title: string;
  created_at?: string; // ISO 8601 string
  updated_at?: string; // ISO 8601 string
  messages?: Message[];
}

export interface ChatCreate {
  title: string;
}

// Message Types
export interface Message {
  id: number;
  chat_id: number;
  sender: string; // "user", "assistant", "system"
  content: string;
  sequence_number: number;
  timestamp?: string; // ISO 8601 string
}

export interface MessageCreate {
  chat_id: number;
  sender: string;
  content: string;
  sequence_number?: number;
}

// Question/Answer Types
export interface Question {
  content: string;
  chat_id?: number;
}

export interface ChatAnswer {
  chat_id: number;
  message_id?: number;
  content: string;
}
