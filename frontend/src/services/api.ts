import axios from 'axios';
import { ApiKey, ApiKeyCreate, SystemConfig, SystemConfigCreate } from '../types/settings';
import { NewsItem } from '../types/news';
import { QAHistoryItem } from '../types/qa';

const API_BASE_URL = 'http://127.0.0.1:8000/api';

const api = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

// News API
export const newsApi = {
    getNewsItems: async (category?: string, source?: string, search?: string) => {
        const params: Record<string, string> = {};
        if (category) params.category = category;
        if (source) params.source = source;
        if (search) params.search = search;

        const response = await api.get<NewsItem[]>('/news/items', { params });
        return response.data;
    },

    getNewsCategories: async () => {
        const response = await api.get<string[]>('/news/categories');
        return response.data;
    },

    getNewsSources: async () => {
        const response = await api.get<string[]>('/news/sources');
        return response.data;
    },
};

// Q&A API
export const qaApi = {
    getQAHistory: async () => {
        const response = await api.get<QAHistoryItem[]>('/qa/history');
        return response.data;
    },
};

// Settings API
export const settingsApi = {
    // API Keys
    getApiKeys: async () => {
        const response = await api.get<ApiKey[]>('/settings/api-keys');
        return response.data;
    },

    getApiKey: async (service: string) => {
        const response = await api.get<ApiKey>(`/settings/api-keys/${service}`);
        return response.data;
    },

    createApiKey: async (apiKey: ApiKeyCreate) => {
        const response = await api.post<ApiKey>('/settings/api-keys', apiKey);
        return response.data;
    },

    updateApiKey: async (service: string, key: string) => {
        const response = await api.put<ApiKey>(`/settings/api-keys/${service}`, { key });
        return response.data;
    },

    deleteApiKey: async (service: string) => {
        const response = await api.delete(`/settings/api-keys/${service}`);
        return response.data;
    },

    // System Config
    getSystemConfigs: async () => {
        const response = await api.get<SystemConfig[]>('/settings/config');
        return response.data;
    },

    getSystemConfig: async (key: string) => {
        const response = await api.get<SystemConfig>(`/settings/config/${key}`);
        return response.data;
    },

    createSystemConfig: async (config: SystemConfigCreate) => {
        const response = await api.post<SystemConfig>('/settings/config', config);
        return response.data;
    },

    updateSystemConfig: async (key: string, value: any) => {
        const response = await api.put<SystemConfig>(`/settings/config/${key}`, { value });
        return response.data;
    },

    deleteSystemConfig: async (key: string) => {
        const response = await api.delete(`/settings/config/${key}`);
        return response.data;
    },
};

export default {
    news: newsApi,
    qa: qaApi,
    settings: settingsApi,
}; 