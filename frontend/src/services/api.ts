// temp/frontend/src/services/api.ts
import axios from 'axios';
// Adjust imports based on the final types needed
import { ApiKeyInfo, ApiKeyCreate, SystemConfig, SystemConfigUpdate } from '../types/settings'; // Assuming settings types are updated
import { NewsItem, NewsCategory, NewsSource, FetchNewsRequest } from '../types/news'; // Use updated NewsItem
import { QAHistory } from '../types/qa'; // Assuming QA types are updated

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api';
console.log('API Base URL:', API_BASE_URL);

const api = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Add interceptor for basic error logging (optional but helpful)
api.interceptors.response.use(
    response => response,
    error => {
        console.error("API Error:", error.response || error.request || error.message);
        // Optionally reformat error before rejecting
        return Promise.reject(error);
    }
);


// --- News API ---
export const newsApi = {
    // Fetch paginated news items
    getNewsItems: async (limit: number = 50, offset: number = 0) => {
        const response = await api.get<NewsItem[]>('/news/items', {
            params: { limit, offset }
        });
        // Ensure date strings are handled correctly if needed later,
        // for now, return as is from backend.
        return response.data;
    },

    // Fetch all categories
    getCategories: async () => {
        // Assuming backend route /api/news/categories returns List[NewsCategory]
        const response = await api.get<NewsCategory[]>('/news/categories');
        return response.data;
    },

    // Fetch all sources
    getSources: async () => {
        // Assuming backend route /api/news/sources returns List[NewsSource]
        const response = await api.get<NewsSource[]>('/news/sources');
        return response.data;
    },

    // Trigger news fetching process (POST request)
    fetchNews: async (request: FetchNewsRequest) => {
        // Backend uses POST /fetch and returns 202 Accepted
        const response = await api.post('/news/fetch', request);
        // Return success message or status code if needed
        return { status: response.status, message: response.data.message };
    },

    // Add other news API calls if needed (delete item, clear all, etc.)
    deleteNewsItem: async (itemId: number) => {
        await api.delete(`/news/items/${itemId}`);
        // No content returned on success (204)
    },

    clearAllNews: async () => {
        const response = await api.delete('/news/items');
        return response.data; // e.g., { message: "..." }
    },
    // Add/Update/Delete for Categories and Sources
};

// --- Q&A API ---
export const qaApi = {
    // Fetch paginated Q&A history
    getQAHistory: async (limit: number = 50, offset: number = 0) => {
        const response = await api.get<QAHistory[]>('/qa/history', {
            params: { limit, offset }
        });
        return response.data;
    },
    // Add other QA API calls if needed (delete item, clear history, POST non-streaming)
    deleteQAHistoryItem: async (qaId: number) => {
        await api.delete(`/qa/history/${qaId}`);
        // No content returned on success (204)
    },
    clearQAHistory: async () => {
        const response = await api.delete('/qa/history');
        return response.data; // e.g., { message: "..." }
    },
};

// --- Settings API ---
export const settingsApi = {
    // API Keys
    getApiKeysInfo: async (): Promise<ApiKeyInfo[]> => {
        // Endpoint returns List[ApiKeyInfo] (name, created_date, modified_date)
        const response = await api.get<ApiKeyInfo[]>('/settings/api-keys');
        return response.data;
    },
    getApiKey: async (apiName: string): Promise<{ api_key: string | null }> => {
        // Endpoint returns {"api_key": "value"} or {"api_key": null}
        const response = await api.get<{ api_key: string | null }>(`/settings/api-keys/${apiName}`);
        return response.data;
    },
    saveApiKey: async (apiKey: ApiKeyCreate): Promise<ApiKeyInfo> => {
        // Endpoint takes ApiKeyCreate, returns ApiKeyInfo of the saved key
        const response = await api.post<ApiKeyInfo>('/settings/api-keys', apiKey);
        return response.data;
    },
    deleteApiKey: async (apiName: string): Promise<void> => {
        await api.delete(`/settings/api-keys/${apiName}`);
        // No content returned on success (204)
    },

    // System Config
    getAllSystemConfigs: async (): Promise<Record<string, any>> => {
        // Endpoint returns Dict[str, Any]
        const response = await api.get<Record<string, any>>('/settings/config');
        return response.data;
    },
    getSystemConfig: async (key: string): Promise<SystemConfig> => {
        // Endpoint returns SystemConfig { config_key: string, config_value: Any }
        const response = await api.get<SystemConfig>(`/settings/config/${key}`);
        return response.data;
    },
    updateSystemConfig: async (key: string, value: any): Promise<SystemConfig> => {
        // Endpoint takes SystemConfigUpdate { config_value: Any }, returns SystemConfig
        const response = await api.put<SystemConfig>(`/settings/config/${key}`, { config_value: value });
        return response.data;
    },
    deleteSystemConfig: async (key: string): Promise<void> => {
        await api.delete(`/settings/config/${key}`);
        // No content returned on success (204)
    },
    resetSystemConfigs: async (): Promise<{ message: string }> => {
        const response = await api.post('/settings/config/reset-defaults');
        return response.data;
    }
};


export default {
    news: newsApi,
    qa: qaApi,
    settings: settingsApi,
};