import api from './api';
import {
  NewsItem,
  NewsCategory,
  NewsItemCreate,
  NewsItemUpdate,
  NewsFilterParams,
  NewsSource,
  NewsSourceCreate,
  NewsSourceUpdate,
  NewsCategoryCreate,
  NewsCategoryUpdate,
  UpdateAnalysisRequest,
  FetchSourceRequest,
  FetchUrlRequest,
  AnalyzeRequest,
  AnalyzeContentRequest
} from '../utils/types';

const BASE_PATH = '/api/news';

// News Categories API
export const getCategories = async (): Promise<NewsCategory[]> => {
  const response = await api.get(`${BASE_PATH}/categories`);
  return response.data;
};

export const createCategory = async (category: NewsCategoryCreate): Promise<NewsCategory> => {
  const response = await api.post(`${BASE_PATH}/categories`, category);
  return response.data;
};

export const updateCategory = async (id: number, category: NewsCategoryUpdate): Promise<NewsCategory> => {
  const response = await api.put(`${BASE_PATH}/categories/${id}`, category);
  return response.data;
};

export const deleteCategory = async (id: number): Promise<void> => {
  await api.delete(`${BASE_PATH}/categories/${id}`);
};

// News Sources API
export const getSources = async (): Promise<NewsSource[]> => {
  const response = await api.get(`${BASE_PATH}/sources`);
  return response.data;
};

export const getSourcesByCategory = async (categoryId: number): Promise<NewsSource[]> => {
  const response = await api.get(`${BASE_PATH}/sources/category/${categoryId}`);
  return response.data;
};

export const getSource = async (sourceId: number): Promise<NewsSource> => {
  const response = await api.get(`${BASE_PATH}/sources/${sourceId}`);
  return response.data;
};

export const createSource = async (source: NewsSourceCreate): Promise<NewsSource> => {
  const response = await api.post(`${BASE_PATH}/sources`, source);
  return response.data;
};

export const updateSource = async (id: number, source: NewsSourceUpdate): Promise<NewsSource> => {
  const response = await api.put(`${BASE_PATH}/sources/${id}`, source);
  return response.data;
};

export const deleteSource = async (id: number): Promise<void> => {
  await api.delete(`${BASE_PATH}/sources/${id}`);
};

// News Items API
export const getNewsItems = async (params: NewsFilterParams): Promise<NewsItem[]> => {
  const response = await api.get(`${BASE_PATH}/items`, { params });
  return response.data;
};

export const getNewsById = async (id: number): Promise<NewsItem> => {
  const response = await api.get(`${BASE_PATH}/items/${id}`);
  return response.data;
};

export const createNewsItem = async (news: NewsItemCreate): Promise<NewsItem> => {
  const response = await api.post(`${BASE_PATH}/items`, news);
  return response.data;
};

export const updateNewsItem = async (id: number, news: NewsItemUpdate): Promise<NewsItem> => {
  const response = await api.put(`${BASE_PATH}/items/${id}`, news);
  return response.data;
};

export const updateNewsAnalysis = async (id: number, data: UpdateAnalysisRequest): Promise<Record<string, string>> => {
  const response = await api.put(`${BASE_PATH}/items/${id}/analysis`, data);
  return response.data;
};

export const deleteNewsItem = async (id: number): Promise<void> => {
  await api.delete(`${BASE_PATH}/items/${id}`);
};

export const clearAllNewsItems = async (): Promise<void> => {
  await api.delete(`${BASE_PATH}/items/clear`);
};

// Task Endpoints
export const fetchAllNews = async (): Promise<Record<string, string>> => {
  const response = await api.post(`${BASE_PATH}/tasks/fetch/all`);
  return response.data;
};

export const fetchNewsFromSource = async (request: FetchSourceRequest): Promise<Record<string, string>> => {
  const response = await api.post(`${BASE_PATH}/tasks/fetch/source`, request);
  return response.data;
};

export const fetchNewsFromUrl = async (request: FetchUrlRequest): Promise<Record<string, any>> => {
  const response = await api.post(`${BASE_PATH}/tasks/fetch/url`, request);
  return response.data;
};

export const fetchNewsFromSourcesBatch = async (sourceIds: number[]): Promise<Record<string, string>> => {
  const response = await api.post(`${BASE_PATH}/tasks/fetch/batch`, {
    source_ids: sourceIds
  });
  return response.data;
};

export const analyzeAllNews = async (request: AnalyzeRequest): Promise<Record<string, string>> => {
  const response = await api.post(`${BASE_PATH}/tasks/analyze/all`, request);
  return response.data;
};

export const analyzeNewsItems = async (request: AnalyzeRequest): Promise<Record<string, string>> => {
  const response = await api.post(`${BASE_PATH}/tasks/analyze/items`, request);
  return response.data;
};

export const analyzeContent = async (request: AnalyzeContentRequest): Promise<Response> => {
  const response = await fetch(`${api.defaults.baseURL}${BASE_PATH}/analyze/content`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`Failed to analyze content: ${response.statusText}`);
  }

  return response;
};


export const streamAnalysis = async (newsId: number, force: boolean = false): Promise<Response> => {
  // --- 1. Get Authentication Token ---
  // Replace this with your actual method of retrieving the stored token
  const token = localStorage.getItem('authToken'); // Or sessionStorage, or from state manager (Pinia, Vuex, etc.)

  if (!token) {
    throw new Error("Authentication token not found.");
  }

  // --- 2. Prepare Request ---
  // Ensure the base URL is correct if your API isn't served from the same origin
  const apiUrl = `${api.defaults.baseURL}${BASE_PATH}/items/${newsId}/analyze/stream?force=${force}`;
  const headers = {
    'Authorization': `Bearer ${token}`,
    'Accept': 'text/plain', // Optional: Indicate expected response type
  };

  // --- 3. Make Fetch Request ---
  // IMPORTANT: Verify the method matches your backend endpoint definition (@router.post)
  const response = await fetch(apiUrl, {
    method: 'POST',
    headers: headers,
    cache: 'no-store', // Important for streaming to prevent caching issues
  });

  if (!response.ok) {
    throw new Error(`Failed to stream analysis: ${response.statusText}`);
  }

  return response;
}; 