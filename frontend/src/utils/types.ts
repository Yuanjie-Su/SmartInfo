// News Category Types
export interface NewsCategory {
  id: number;
  name: string;
}

export interface NewsCategoryCreate {
  name: string;
}

// News Source Types
export interface NewsSource {
  id: number;
  name: string;
  url: string;
  category_id: number;
  category?: NewsCategory;
}

export interface NewsSourceCreate {
  name: string;
  url: string;
  category_id: number;
}

// News Types
export interface News {
  id: number;
  source_id?: number;
  title: string;
  content?: string;
  summary?: string;
  url: string;
  source_name: string;
  category_name: string; 
  category_id?: number;
  analysis?: string;
  date?: string;
  source?: NewsSource;
}

export interface NewsCreate {
  source_id?: number;
  title: string;
  content?: string;
  summary?: string;
  url: string;
  source_name: string;
  category_name: string;
  category_id?: number;
  analysis?: string;
  date?: string;
}

export interface NewsFilterParams {
  category_id?: number;
  source_id?: number;
  has_analysis?: boolean;
  page?: number;
  page_size?: number;
  search_term?: string;
}

export interface NewsAnalysisRequest {
  news_ids?: number[];
  analyze_all?: boolean;
  force_reanalyze?: boolean;
}

// API Key Types
export interface ApiKey {
  id: number;
  api_name: string;
  api_key: string;
  description?: string;
  created_date?: number;
  modified_date?: number;
}

export interface ApiKeyCreate {
  api_name: string;
  api_key: string;
  description?: string;
}

// System Config Types
export interface SystemConfig {
  config_key: string;
  config_value: string;
  description?: string;
}

export interface SystemConfigCreate {
  config_key: string;
  config_value: string;
  description?: string;
}

// Chat Types
export interface Chat {
  id: number;
  title: string;
  system_prompt?: string;
  model_name?: string;
  metadata?: string;
  created_at?: number;
  updated_at?: number;
  messages?: Message[];
}

export interface ChatCreate {
  title: string;
  system_prompt?: string;
  model_name?: string;
  metadata?: string;
}

// Message Types
export interface Message {
  id: number;
  chat_id: number;
  sender: string; // "user", "assistant", "system"
  content: string;
  sequence_number?: number;
  timestamp?: number;
  metadata?: string;
}

export interface MessageCreate {
  chat_id: number;
  sender: string;
  content: string;
  sequence_number?: number;
  metadata?: string;
}

// Chat Question/Answer Types
export interface ChatQuestion {
  chat_id?: number;
  content: string;
  system_prompt?: string;
  model_name?: string;
}

export interface ChatAnswer {
  chat_id?: number;
  message_id?: number;
  content: string;
  metadata?: Record<string, any>;
}

// Settings Update Types
export interface SettingsUpdate {
  settings: Record<string, any>;
} 